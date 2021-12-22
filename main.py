import asyncio
from datetime import datetime
from uuid import uuid4

import asyncpg
from aiogram import Bot
from aiogram import Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import BotCommand
from aiogram.types import ReplyKeyboardMarkup

bot = Bot(token="5048772657:AAHDLTGdePpLHpkbLKFynTT4jPpx9ks3fys")
dp = Dispatcher(bot, storage=MemoryStorage())


class Order(StatesGroup):
    movie = State()
    cinema = State()
    session = State()
    seat = State()


async def connect():
    db = await asyncpg.connect("postgresql://u_test:testpwd@92.242.58.173:1984/db_test")
    return db


async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await bot.send_message(message.from_user.id,
                           '👋🏻 Привет!\n\nЯ бот проекта NavMovie, помогаю с покупкой билетов в кино '
                           'онлайн. Чтобы пройти регистрацию, напиши /reg')


async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Действие отменено", reply_markup=types.ReplyKeyboardRemove())


async def cmd_reg(message: types.Message):
    db = await connect()
    try:
        await db.execute('''INSERT INTO nav_movie.users(id, first_name, last_name) VALUES($1, $2, $3)''',
                         int(message.from_user.id), message.from_user.first_name, message.from_user.last_name)
        await db.close()
    except Exception:
        await bot.send_message(message.from_user.id, '👀 Кажется, вы уже зарегистрированы! '
                                                     ' \n\nВведите команду /help для получения '
                                                     'подробностей о возможностях бота.')
    else:
        await bot.send_message(message.from_user.id, 'Регистрация пройдена 🎉 \nВведите команду /help для получения '
                                                     'подробностей о возможностях бота.')


async def cmd_help(message: types.Message):
    await bot.send_message(message.from_user.id,
                           '/movies - выбрать фильм\n/cinemas - выбрать кинотеатр\n/popular - посмотреть топ фильмы')


# NEW
async def cmd_popular(message: types.Message):
    db = await connect()
    best_movie = []
    id_session_order = await db.fetch(
        '''SELECT movie_id FROM nav_movie.sessions 
        WHERE nav_movie.sessions.id IN (SELECT session_id FROM nav_movie.orders)''')

    if len(id_session_order) < 3:
        await bot.send_message(message.from_user.id, f'🎬 Слишком мало заказов для анализа :(')
        await db.close()

    best_movie.append(await db.fetch('''SELECT name FROM nav_movie.movie WHERE 
        nav_movie.movie.id = $1''', dict(id_session_order[0])['movie_id']))

    best_movie.append(await db.fetch('''SELECT name FROM nav_movie.movie WHERE 
            nav_movie.movie.id = $1''', dict(id_session_order[1])['movie_id']))

    best_movie.append(await db.fetch('''SELECT name FROM nav_movie.movie WHERE 
                nav_movie.movie.id = $1''', dict(id_session_order[2])['movie_id']))

    await db.close()

    message.text = '\n1. ' + dict(best_movie[0][0])['name'] + '\n2. ' + dict(best_movie[1][0])['name'] + \
                   '\n3. ' + dict(best_movie[2][0])['name']
    # dict(best_movie[1])['name']

    await bot.send_message(message.from_user.id, f'🎬 Вот три лучших фильма за последнее время: \n {message.text}')
    # await bot.send_message(message.from_user.id, f'Вы выбрали сеанс - {message.text}')


async def movies(message: types.Message):
    db = await connect()
    movies_names = await db.fetch(
        '''SELECT name, id FROM nav_movie.movie 
        WHERE nav_movie.movie.rental_start < CURRENT_DATE''')
    await db.close()

    db2 = await connect()
    free_movies = await db2.fetch(
        '''SELECT movie_id FROM nav_movie.sessions WHERE nav_movie.sessions.session_date = CURRENT_DATE 
        AND nav_movie.sessions.session_time > CURRENT_TIME''')
    await db2.close()

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    for movie in movies_names:
        for free in free_movies:
            if int(movie['id']) == int(free['movie_id']):
                keyboard.add(dict(movie)['name'])

    keyboard.add('Отмена')
    await bot.send_message(message.from_user.id, '🍿 Список фильмов в прокате', reply_markup=keyboard)
    await Order.movie.set()


async def cinemas(message: types.Message):
    db = await connect()
    cinemas_names = await db.fetch('''SELECT name, id FROM nav_movie.cinema''')
    await db.close()

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for cinema in cinemas_names:
        keyboard.add(dict(cinema)['name'])
    keyboard.add('Отмена')

    await bot.send_message(message.from_user.id, '🎥 Доступные кинотеатры', reply_markup=keyboard)
    await Order.cinema.set()


async def sessions(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    db = await connect()
    sessions_names = await db.fetch('''SELECT session_date, session_time, id FROM nav_movie.sessions WHERE 
    nav_movie.sessions.movie_id = (SELECT id FROM nav_movie.movie WHERE nav_movie.movie.name = $1) AND 
    nav_movie.sessions.cinema_hall_id IN ( SELECT id FROM nav_movie.cinema_hall WHERE nav_movie.cinema_hall.cinema_id = 
    (SELECT id FROM nav_movie.cinema WHERE nav_movie.cinema.name = $2))''',
                                    user_data['choosen_movie'], user_data['choosen_cinema'])
    await db.close()
    result = sessions_names
    for session_name in result:
        if str(dict(session_name)['session_date']) < str(datetime.now().date()) or (
                str(dict(session_name)['session_date']) == str(datetime.now().date()) and
                str(dict(session_name)['session_time']) < str(datetime.now().time())):
            if session_name in result:
                result.remove(session_name)
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    if not result:
        await bot.send_message(message.from_user.id, 'Сеансов нет :(\n Выберите другой фильм.')
        await movies(message)
        return
    for session in result:
        keyboard.add(f"{dict(session)['session_date']} {dict(session)['session_time']}")
    keyboard.add('Отмена')
    await bot.send_message(message.from_user.id, '🍿 Доступные сеансы', reply_markup=keyboard)
    await Order.session.set()


async def seat(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    db = await connect()
    seats = await db.fetch('''SELECT seat_row, seat_column, id FROM nav_movie.seat WHERE nav_movie.seat.id IN
    (SELECT seat_id FROM nav_movie.cinema_hall_seat WHERE nav_movie.cinema_hall_seat.cinema_hall_id IN
        (SELECT id FROM nav_movie.cinema_hall WHERE id IN (SELECT cinema_hall_id FROM nav_movie.sessions WHERE 
        nav_movie.sessions.movie_id IN (SELECT id FROM nav_movie.movie WHERE nav_movie.movie.name = $3) AND 
                nav_movie.sessions.session_date = $1 AND nav_movie.sessions.session_time = $2) 
                AND nav_movie.cinema_hall.cinema_id = (SELECT id FROM nav_movie.cinema WHERE 
                nav_movie.cinema.name = $4)))''',
                           datetime.strptime(user_data['choosen_session'].split()[0], "%Y-%m-%d"),
                           datetime.strptime(user_data['choosen_session'].split()[1], "%H:%M:%S"),
                           user_data['choosen_movie'],
                           user_data['choosen_cinema'])
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    orders = await db.fetch('''SELECT nav_movie.seat.seat_row, nav_movie.seat.seat_column, nav_movie.sessions.session_date,
         nav_movie.sessions.session_time, nav_movie.cinema.name AS cinema_name, nav_movie.movie.name AS movie_name FROM nav_movie.seat, 
         nav_movie.sessions, nav_movie.cinema, nav_movie.movie WHERE (nav_movie.seat.id IN (SELECT seat_id FROM 
         nav_movie.orders)) AND (nav_movie.movie.id IN (SELECT movie_id FROM nav_movie.sessions WHERE 
         nav_movie.sessions.id IN (SELECT session_id FROM nav_movie.orders))) AND (nav_movie.cinema.id IN (SELECT cinema_id FROM 
         nav_movie.cinema_hall WHERE nav_movie.cinema_hall.id IN (SELECT cinema_hall_id FROM nav_movie.sessions WHERE 
         nav_movie.sessions.id IN (SELECT session_id FROM nav_movie.orders))))''')
    await db.close()
    result = seats
    for order in orders:
        if (user_data['choosen_session'].split()[0] == str(dict(order)['session_date']) and
            user_data['choosen_session'].split()[1] == str(dict(order)['session_time'])
            and user_data['choosen_movie'] == dict(order)['movie_name'] and user_data['choosen_cinema'] ==
            dict(order)['cinema_name']) or (str(dict(order)['session_date']) < str(datetime.now().date()) or
                                            (str(dict(order)['session_date']) == str(datetime.now().date()) and
                                             str(dict(order)['session_time']) < str(datetime.now().time()))):
            for seat in seats:
                if (dict(seat)['seat_row'] == dict(order)['seat_row'] and dict(seat)['seat_column'] ==
                        dict(order)['seat_column']):
                    order = dict(order)
                    order['session_date'] = str(order['session_date'])
                    order['session_time'] = str(order['session_time'])
                    if seat in result:
                        result.remove(seat)
    if not result:
        await bot.send_message(message.from_user.id, 'Свободных мест нет :(\nВыберите другой сеанс.')
        await sessions(message, state)
        return
    for seat in result:
        seat = dict(seat)
        keyboard.add(f"Ряд: {seat['seat_row']}, место: {seat['seat_column']}")

    keyboard.add('Отмена')
    await bot.send_message(message.from_user.id, '👀 Доступные места', reply_markup=keyboard)
    await Order.seat.set()


async def order(message: types.Message, state: FSMContext):
    user_data = await state.get_data()

    user_data['choosen_seat'] = user_data['choosen_seat'].replace('Ряд: ', '')
    user_data['choosen_seat'] = user_data['choosen_seat'].replace('место: ', '')

    row, column = user_data['choosen_seat'].split(', ')
    db = await connect()
    cinema_commission = await db.fetch('''SELECT commission FROM nav_movie.cinema WHERE nav_movie.cinema.name = $1''',
                                       user_data['choosen_cinema'])
    seat_price = await db.fetch('''SELECT price, id FROM nav_movie.seat WHERE nav_movie.seat.seat_column = $1 AND 
    nav_movie.seat.seat_row = $2''', int(column), int(row))
    session_price = await db.fetch('''SELECT price, id FROM nav_movie.sessions WHERE nav_movie.sessions.movie_id IN
          (SELECT id FROM nav_movie.movie WHERE nav_movie.movie.name = $1) AND nav_movie.sessions.session_date = $2 
          AND nav_movie.sessions.session_time = $3''',
                                   user_data['choosen_movie'],
                                   datetime.strptime(user_data['choosen_session'].split()[0], "%Y-%m-%d"),
                                   datetime.strptime(user_data['choosen_session'].split()[1], "%H:%M:%S"))

    result_price = dict(cinema_commission[0])['commission'] + dict(seat_price[0])['price'] + \
                   dict(session_price[0])['price']
    date = datetime.strptime(user_data['choosen_session'].split()[0], "%Y-%m-%d").strftime("%d.%m")
    result_msg = f"Ваш заказ № {uuid4()} сформирован 🎉\n\nСумма к оплате: {result_price} рублей.\n\nЖдем вас {date} в кинотеатре " \
                 f"{user_data['choosen_cinema']} в " \
                 f"{user_data['choosen_session'].split()[1]}. \nОплата будет на кассе, приходите заранее! 🍿" \
                 f"\n\nВернуться в меню функций: /help"
    await db.execute('''INSERT INTO nav_movie.orders(price, seat_id, user_id, session_id) VALUES ($1, $2, $3, $4)''',
                     result_price, dict(seat_price[0])['id'], message.from_user.id, dict(session_price[0])['id'])
    await db.close()
    await bot.send_message(message.from_user.id, result_msg, reply_markup=types.ReplyKeyboardRemove())
    await state.finish()


async def seat_chosen(message: types.Message, state: FSMContext):
    if message.text.lower() == 'отмена' or message.text.lower() == '/cancel':
        await cmd_cancel(message, state)
        return
    user_data = await state.get_data()
    db = await connect()
    seats = await db.fetch('''SELECT seat_row, seat_column FROM nav_movie.seat WHERE nav_movie.seat.id IN
        (SELECT seat_id FROM nav_movie.cinema_hall_seat WHERE nav_movie.cinema_hall_seat.cinema_hall_id IN
            (SELECT id FROM nav_movie.cinema_hall WHERE id IN
                (SELECT cinema_hall_id FROM nav_movie.sessions WHERE nav_movie.sessions.movie_id IN
                    (SELECT id FROM nav_movie.movie WHERE nav_movie.movie.name = $3) AND 
                    nav_movie.sessions.session_date = $1 AND nav_movie.sessions.session_time = $2)
                            AND nav_movie.cinema_hall.cinema_id = (SELECT id FROM nav_movie.cinema WHERE 
                            nav_movie.cinema.name = $4)))''',
                           datetime.strptime(user_data['choosen_session'].split()[0], "%Y-%m-%d"),
                           datetime.strptime(user_data['choosen_session'].split()[1], "%H:%M:%S"),
                           user_data['choosen_movie'], user_data['choosen_cinema'])
    await db.close()
    result = []
    for seat in seats:
        result.append(f"Ряд: {dict(seat)['seat_row']}, место: {dict(seat)['seat_column']}")
    if message.text not in result:
        await message.answer("Пожалуйста, выберите место, используя клавиатуру ниже или отмените действие.")
        return
    await bot.send_message(message.from_user.id, f'Вы выбрали - {message.text}')
    await state.update_data(choosen_seat=message.text)
    await order(message, state)


async def session_chosen(message: types.Message, state: FSMContext):
    if message.text.lower() == 'отмена' or message.text.lower() == '/cancel':
        await cmd_cancel(message, state)
        return
    user_data = await state.get_data()
    db = await connect()
    sessions_names = await db.fetch('''SELECT session_date, session_time, id FROM nav_movie.sessions WHERE 
        nav_movie.sessions.movie_id = (SELECT id FROM nav_movie.movie WHERE nav_movie.movie.name = $1) AND 
        nav_movie.sessions.cinema_hall_id IN ( SELECT id FROM nav_movie.cinema_hall
         WHERE nav_movie.cinema_hall.cinema_id = (SELECT id FROM nav_movie.cinema WHERE nav_movie.cinema.name = $2))''',
                                    user_data['choosen_movie'], user_data['choosen_cinema'])
    await db.close()
    result = []
    for session_name in sessions_names:
        result.append(f"{dict(session_name)['session_date']} {dict(session_name)['session_time']}")
    if message.text not in result:
        await message.answer("Пожалуйста, выберите сеанс, используя клавиатуру ниже или отмените действие.")
        return
    await bot.send_message(message.from_user.id, f'Вы выбрали сеанс - {message.text}')
    await state.update_data(choosen_session=message.text)
    await seat(message, state)


async def movie_chosen(message: types.Message, state: FSMContext):
    if message.text.lower() == 'отмена' or message.text.lower() == '/cancel':
        await cmd_cancel(message, state)
        return

    db = await connect()
    movies_names = await db.fetch(
        '''SELECT name FROM nav_movie.movie''')
    await db.close()

    result = []
    for movie_name in movies_names:
        result.append(dict(movie_name)['name'])

    if message.text not in result:
        await message.answer("Пожалуйста, выберите фильм, используя клавиатуру ниже или отмените действие.")
        return

    await bot.send_message(message.from_user.id, f'Вы выбрали фильм - {message.text}')

    await state.update_data(choosen_movie=message.text)
    user_data = await state.get_data()

    if user_data.get('choosen_cinema'):
        await sessions(message, state)
    else:
        await cinemas(message)


async def cinema_chosen(message: types.Message, state: FSMContext):
    if message.text.lower() == 'отмена' or message.text.lower() == '/cancel':
        await cmd_cancel(message, state)
        return

    db = await connect()
    cinemas_names = await db.fetch(
        '''SELECT name FROM nav_movie.cinema''')
    await db.close()
    result = []

    for cinema_name in cinemas_names:
        result.append(dict(cinema_name)['name'])

    if message.text not in result:
        await message.answer("Пожалуйста, выберите кинотеатр, используя клавиатуру ниже или отмените действие.")
        return

    await bot.send_message(message.from_user.id, f'Вы выбрали кинотеатр - {message.text}')
    await state.update_data(choosen_cinema=message.text)
    user_data = await state.get_data()

    if user_data.get('choosen_movie'):
        await sessions(message, state)
    else:
        await movies(message)


def register_handlers():
    dp.register_message_handler(movies, commands="movies", state="*")
    dp.register_message_handler(cinemas, commands="cinemas", state="*")
    dp.register_message_handler(movie_chosen, state=Order.movie)
    dp.register_message_handler(cinema_chosen, state=Order.cinema)
    dp.register_message_handler(session_chosen, state=Order.session)
    dp.register_message_handler(seat_chosen, state=Order.seat)


def register_handlers_common():
    dp.register_message_handler(cmd_start, commands="start", state="*")
    dp.register_message_handler(cmd_cancel, commands="cancel", state="*")
    dp.register_message_handler(cmd_cancel, Text(equals="отмена", ignore_case=True), state="*")
    dp.register_message_handler(cmd_reg, commands="reg", state="*")
    dp.register_message_handler(cmd_help, commands="help", state="*")
    # NEW
    dp.register_message_handler(cmd_popular, commands="popular", state="*")


async def set_commands():
    commands = [
        BotCommand(command="/movies", description="Выбрать фильм"),
        BotCommand(command="/cinemas", description="Выбрать кинотеатр"),
        BotCommand(command="/reg", description="Регистрация"),
        BotCommand(command="/help", description="Помощь"),
        BotCommand(command="/cancel", description="Отменить текущее действие"),
        # NEW
        BotCommand(command="/popular", description="Популярные фильмы")
    ]
    await bot.set_my_commands(commands)


async def main():
    await set_commands()
    await dp.start_polling()


if __name__ == "__main__":
    # Запуск бота
    register_handlers()
    register_handlers_common()
    asyncio.run(main())
