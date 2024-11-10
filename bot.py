import telebot
from telebot import types
import logging
import sqlite3
import time
import threading
import requests
import firebase_admin
import os
from firebase_admin import credentials, db, storage
import random
import re
import json
# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

cred = credentials.Certificate("privKey/tours-in-buenos-aires-firebase-adminsdk-yqt2b-5f2d7a4242.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://tours-in-buenos-aires-default-rtdb.firebaseio.com',
    'storageBucket': 'stours-in-buenos-aires.appspot.com'
})

database = db.reference()
bucket = storage.bucket('tours-in-buenos-aires.appspot.com')

bot = telebot.TeleBot('7346257604:AAGqNiMLG1qnHIMFyytYbvdN6CYwrM17EHY')  # Замените YOUR_API_KEY на ваш ключ
language = {}
code_entering = {}

user_state = {}
user_data = {}

all_excursions = {}
block_name = {} # Для замены и модификации
NOACT, PIN, START, ADDMIN_CODE, ADD_BLOCK_CODE, TOUR_CODE, CHOOSE_LANGUAGE, ADD_BLOCK_NAME, ADD_DESCRIPTION_MAIN, ADD_ORDER, CONF_AUDIO, ADD_AUDIO, CONF_PHOTO, ADD_PHOTO, ADDMIN_CODE_SAVE, SHORT_NAME, ADD_DESCRIPTION, CONFIRM_AUDIO = range(18)

MESSAGE_IDS_FILE = "message_ids.json"
commands = [
    types.BotCommand("start", "Запустить бота")
    #,
    #types.BotCommand("help", "Помощь по боту"),
    #types.BotCommand("settings", "Настройки")
]

bot.set_my_commands(commands)

def add_message_id(chat_id, message_id):
    try:
        with open(MESSAGE_IDS_FILE, "r") as file:
            data = json.load(file)
    except FileNotFoundError:
        data = {}
    
    # Преобразуем chat_id в строку, чтобы использовать его как ключ JSON
    chat_id_str = str(chat_id)
    if chat_id_str not in data:
        data[chat_id_str] = []
    
    # Проверка, есть ли уже message_id в списке перед добавлением
    if message_id not in data[chat_id_str]:
        data[chat_id_str].append(message_id)

    # Перезаписываем файл с обновлёнными данными
    with open(MESSAGE_IDS_FILE, "w") as file:
        json.dump(data, file)

def generate_random_code():
    """Генерирует случайный 4-значный код, состоящий из цифр."""
    return ''.join(random.choices("0123456789", k=4))

def reset_all_codes():
    """Сбрасывает значение `block_id` для всех `blocks` на новый случайный код."""
    blocks_ref = database.child('blocks').get()

    if blocks_ref:  # Проверяем, что блоки существуют
        for block_id, block_data in blocks_ref.items():
            new_code = generate_random_code()
            # Создаём новый блок с новым кодом и существующими данными, а затем удаляем старый блок
            database.child('blocks').child(new_code).set(block_data)
            database.child('blocks').child(block_id).delete()
            #print(f"Код для блока {block_id} изменён на {new_code}")
    #else:
        #print("Блоки не найдены в базе данных.")

    #print("Процесс обновления кодов завершён.")

# Добавление chat_id пользователя в файл
def clear_message_ids_file():
    """Очищает JSON файл, перезаписывая его пустым объектом."""
    with open(MESSAGE_IDS_FILE, "w") as file:
        json.dump({}, file)

# Функция для удаления сообщений из файла
def delete_messages():
    try:
        with open(MESSAGE_IDS_FILE, "r") as file:
            message_data = json.load(file)
    except FileNotFoundError:
        #print("Файл с ID сообщений не найден.")
        return

    for chat_id, message_ids in message_data.items():
        failed_deletions = []
        for message_id in message_ids:
            try:
                bot.delete_message(chat_id, message_id)
                #print(f"Сообщение {message_id} в чате {chat_id} успешно удалено.")
            except telebot.apihelper.ApiException as e:
                # Логика для обработки ошибок удаления
                error_message = str(e)
                if "message to delete not found" in error_message or "message can't be deleted" in error_message:
                    print(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {error_message}")
                else:
                    failed_deletions.append(message_id)

        # Удаляем из данных сообщения, которые успешно удалены
        message_data[chat_id] = failed_deletions

    # Перезаписываем JSON-файл после завершения попыток удаления
    with open(MESSAGE_IDS_FILE, "w") as file:
        json.dump(message_data, file)
    #print("Удаление сообщений завершено, файл обновлен.")

# Загрузка кода администратора из файла при запуске бота
def load_admin_code():
    global adm_code
    if os.path.exists("admin_code.txt"):
        with open("admin_code.txt", "r") as file:
            adm_code = file.read().strip()
    else:
        adm_code = "123456"  # Установите начальное значение, если файла нет

# Сохранение нового кода администратора в файл
def save_admin_code(new_code):
    with open("admin_code.txt", "w") as file:
        file.write(new_code)

# Загружаем админский код при запуске бота
load_admin_code()

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start(message):
    # Создание кнопок для выбора языка
    bot.send_message(message.chat.id, "¡Bienvenido!", reply_markup=types.ReplyKeyboardRemove())
    global code_entering, user_state, all_excursions, block_name, chat_ids_users 
    block_name[message.chat.id] = ""
    code_entering[message.chat.id] = 0
    markup2 = types.InlineKeyboardMarkup()
    
    btn1 = types.InlineKeyboardButton("Español 🇦🇷", callback_data="language_spanish")
    btn2 = types.InlineKeyboardButton("English 🇺🇸", callback_data="language_english")
    btn3 = types.InlineKeyboardButton("Русский 🇷🇺", callback_data="language_russian")
    
    markup2.add(btn1, btn2, btn3)
    bot.send_message(message.chat.id, text="Por favor, seleccione su idioma 🇦🇷 \nPlease, choose your language 🇺🇸 \nПожалуйста, выберите язык 🇷🇺 ", reply_markup=markup2)
    logger.info(f"Displayed language options to {message.from_user.first_name}.")
    user_state[message.chat.id] = NOACT

# Обработчик выбора языка
@bot.callback_query_handler(func=lambda call: call.data.startswith("language_"))
def handle_language_selection(call):
    global language  # Делаем переменную глобальной, чтобы можно было использовать в других функциях
    language[call.message.chat.id] = call.data.split("_")[1]
    global code_entering, user_state
    code_entering[call.message.chat.id] = 0
    enter_code(call.message)
    logger.info(f"{call.from_user.first_name} selected language: {language[call.message.chat.id].capitalize()}.")

# Функция для ввода кода после выбора языка
def enter_code(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    global code_entering, all_excursions 
    all_excursions[message.chat.id] = database.child('blocks').get()
    code_entering[message.chat.id] = 1
    if language[message.chat.id] == "spanish":
        but = "Volver a la selección de idioma"
        resp = "Ingrese el código de excursión. Si no lo conoces ¡pregúntale a tu guía!"
    elif language[message.chat.id] == "english":
        but ="Return to language selection"
        resp = "Enter the tour code. If you don't know it, ask the guide!"
    elif language[message.chat.id] == "russian":
        but ="Вернуться к выбору языка"
        resp = "Введите код экскурсии. Если он вам неизвестен, спросите у гида!"
    button1 = types.KeyboardButton(but)
    markup.add(button1)
    bot.send_message(message.chat.id, text=resp, reply_markup=markup)
    logger.info(f"Prompted {message.from_user.first_name} to enter code in {language[message.chat.id].capitalize()}.")
    user_state[message.chat.id] = NOACT

def enter_code_repeat(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    global code_entering
    code_entering[message.chat.id] = 1
    if language[message.chat.id] == "spanish":
        but = "Volver a la selección de idioma"
        resp = "Intentar otra vez"
    elif language[message.chat.id] == "english":
        but ="Return to language selection"
        resp = "Try again"
    elif language[message.chat.id] == "russian":
        but ="Вернуться к выбору языка"
        resp = "Попробуйте снова"
    button1 = types.KeyboardButton(but)
    markup.add(button1)
    bot.send_message(message.chat.id, text=resp, reply_markup=markup)
    logger.info(f"Prompted {message.from_user.first_name} to enter code in {language[message.chat.id].capitalize()}.")

@bot.message_handler(func=lambda message: message.text in ("Gestión de excursiones", "Excursion management", "Управление экскурсиями"))
def admin_pannel(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        b1 = types.KeyboardButton("Lista de excursiones")
        b2 = types.KeyboardButton("Agregar un recorrido")
        b3 = types.KeyboardButton("Actualizar códigos de tour")
        b4 = types.KeyboardButton("Cambiar el código de administrador")
        b5 = types.KeyboardButton("Instruccion")
        b6 = types.KeyboardButton("Salida")
        markup.row(b1, b2)
        markup.row(b3, b4)
        markup.row(b5)
        markup.row(b6)
        bot.send_message(
            message.chat.id,
            text="¡Excelente!\n"
                 "Esta es la ventana de gestión de excursiones. Para obtener más información sobre las capacidades del administrador, puede hacer clic en el botón 'Instrucciones'\n"
                 "Si tienes alguna otra pregunta, escribe al desarrollador https://t.me/The_lord_of_the_dawn",
            reply_markup=markup
        )
    elif language[message.chat.id] == "english":
        b1 = types.KeyboardButton("List of tours")
        b2 = types.KeyboardButton("Add a tour")
        b3 = types.KeyboardButton("Update tour codes")
        b4 = types.KeyboardButton("Edit the admin code")
        b5 = types.KeyboardButton("Instruction")
        b6 = types.KeyboardButton("Exit")
        markup.row(b1, b2)
        markup.row(b3, b4)
        markup.row(b5)
        markup.row(b6)
        bot.send_message(
            message.chat.id,
            text="Great!\n"
                 "This is the excursion management window. To learn more about the admin's capabilities, you can click on the 'Instructions' button\n"
                 "If you have any other questions, write to the developer https://t.me/The_lord_of_the_dawn",
            reply_markup=markup
        )
    elif language[message.chat.id] == "russian":
        b1 = types.KeyboardButton("Список экскурсий")
        b2 = types.KeyboardButton("Добавить тур")
        b3 = types.KeyboardButton("Обновить коды экскурсий")
        b4 = types.KeyboardButton("Смена админского кода")
        b5 = types.KeyboardButton("Инструкция")
        b6 = types.KeyboardButton("Выход")
        markup.row(b1, b2)
        markup.row(b3, b4)
        markup.row(b5)
        markup.row(b6)
        bot.send_message(
            message.chat.id,
            text="Отлично!\n"
                 "Это окно управления экскурсиями. Чтобы узнать подробнее о возможностях админа, вы можете кликнуть на кнопку 'Инструкция'\n"
                 "Если есть другие вопросы, пишите разработчику https://t.me/The_lord_of_the_dawn",
            reply_markup=markup
        )
    user_state[message.chat.id] = START

@bot.message_handler(func=lambda message: message.text in ("Инструкция", "Instruction", "Instruccion"))
def instruction(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    lang = language.get(message.chat.id, "english")
    
    # Устанавливаем текст кнопки в зависимости от языка
    back_button_text = {
        "spanish": "Volver a la ventana de control",
        "english": "Return to the control window",
        "russian": "Вернуться в окно управления"
    }.get(lang, "Return to the control window")
    
    b1 = types.KeyboardButton(back_button_text)
    markup.row(b1)
    
    # Инструкции на каждом языке
    instructions_text = {
    "spanish": ("Entonces, hay 6 botones en el menú.\n\n"
    "'Salir' lo llevará a la ventana de selección de idioma.\n\n"
    "'Instrucciones': abre las instrucciones que estás leyendo actualmente.\n\n"
    "'Lista de excursiones' - le enviará a una ventana donde en los botones verá las excursiones ya añadidas con sus códigos. Al hacer clic en "
    "en el botón con el nombre de la excursión (si la excursión existe en ruso, su nombre se muestra automáticamente en el botón "
    "en ruso) mostrará el recorrido completo en todos los idiomas agregados, después de lo cual aparecerán los botones 'Eliminar' y 'Cambiar' "
    "El botón 'Eliminar' - después de la confirmación - borrará la excursión de la base de datos. 'Editar' - lo llevará al menú del editor. "
    "Podrás agregar un nuevo idioma para el tour (si no se ha agregado ya todo el ruso, inglés y español) o editar "
    "un recorrido en el idioma seleccionado en el que el recorrido ya existe. Si elige editar el recorrido, habrá un menú disponible para usted "
    "un editor completo para el título, descripción y por separado para cada bloque de excursión. También puedes eliminar una excursión en un idioma determinado."
    "y también agregar o eliminar un bloque de excursión. Lea atentamente las instrucciones del bot y "
    "use botones a menos que el bot solicite lo contrario. Normalmente, este tipo de solicitud contendrá la palabra 'Entrar'.\n\n"
    "'Agregar recorrido': esta es la función de agregar una excursión. Agregará secuencialmente código, idioma, nombre de la excursión (en un idioma determinado) "
    "descripción de la excursión (en un idioma determinado), nombre corto del bloque de excursión, audio (si es necesario), foto (si es necesario) "
    "el número de serie del bloque de excursión (Agregue el número de serie del bloque con mucho cuidado. Comience siempre con uno y "
    "A medida que agregas cada bloque siguiente, ve en orden ascendente uno [1, 2, 3...] hasta terminar de agregar un recorrido en ese idioma "
    "Al agregar un nuevo idioma para una excursión, comience a numerar primero según el mismo esquema. Mantenga constante el orden de los bloques de excursión "
    "entre idiomas. El número de serie no sólo se encarga de ordenar los bloques de excursiones dentro de un idioma, sino que también se muestra en los botones para seleccionar uno específico "
    "puntos de cliente) y "
    "descripción del bloque. Tenga mucho cuidado al agregar una excursión. Lea atentamente los mensajes del chat sobre qué es exactamente "
    "Actualmente le pide que agregue. Si comete un error, agregue el archivo incorrecto o agregue archivos en el orden incorrecto "
    "en el que el bot los solicite, tendrás que agregarlo nuevamente o ir al editor de excursiones si has agregado un recorrido "
    "De una forma u otra, si aún cometes un error y el bot se congela, haz clic en el menú a la derecha de la ventana de entrada de texto y haz clic en /iniciar.\n\n"
    "'Actualizar códigos de excursión': esta función actualizará automáticamente los códigos de excursión y eliminará todos los archivos de excursión para los usuarios "
    "Puedes consultar nuevos códigos en la ventana 'Lista de excursiones'. Recomendación: actualiza los códigos después de cada excursión "
    "El bot tiene un límite de tiempo para almacenar los ID de los mensajes. La función no funciona instantáneamente, así que al restablecer los códigos, tenga paciencia "
    "Puede tardar entre dos y tres minutos.\n\n"
    "'Cambiar código de administrador': puede cambiar el código de administrador en esta ventana manualmente. ¡No lo pierda! "
    "Sólo el desarrollador del bot puede restaurar este código.\n\n"
    "Para todas las preguntas que surjan, así como en caso de recomendaciones para mejorar la funcionalidad o el soporte de texto del bot, "
    "Comuníquese con el desarrollador cuyo enlace de perfil está publicado en el menú de administración principal. ¡Le deseo buena suerte!"
    ),
    "english": (
        "So, there are 6 buttons in the menu.\n\n"
        "'Exit' -- will send you to the language selection window.\n\n"
        "'Instructions' -- opens the instruction that you are reading now.\n\n"
        "'List of excursions' -- will send you to a window where you will see the already added excursions with their codes on the buttons. By clicking "
    "on the button with the excursion name (if the excursion exists in Russian, its name on the button is automatically displayed in "
    "Russian) you will display the full excursion in all added languages, after which the 'Delete' and 'Edit' buttons will appear. "
    "The 'Delete' button -- after confirmation - will erase the excursion from the database. 'Edit' -- will transfer you to the editor menu. "
    "You will be able to add a new language for the excursion (if not all of Russian, English and Spanish have already been added) or edit the "
    "excursion in the selected language in which the tour already exists. If you select to edit a tour -- you will have access to the full "
    "editor menu for the title, description, and each tour block separately. You will also be able to delete a tour in this language, "
    "as well as add or delete a tour block. Please read the bot's instructions carefully and "
    "use the buttons unless the bot asks otherwise. Typically, a request of this kind contains the word 'Enter'.\n\n"
    "'Add tour' -- This is the function for adding a tour. You will sequentially add the code, language, tour title (in this language), "
    "tour description (in this language), short title for the tour block, audio (if required), photo (if required),"
    "tour block ordinal number (Please, add the block ordinal number very carefully. Always start with one and "
    "when adding each subsequent block, go incrementally by one [1, 2, 3 ...] until you finish adding the tour in this language. "
    "When adding a new tour language, start numbering from the beginning according to the same scheme. Keep the order of the tour blocks consistent between "
    "languages. The ordinal number is not only responsible for sorting the tour blocks within the language, but is also displayed on the buttons for selecting a specific"
    "point for clients) and "
    "block description. Please, be very careful when adding a tour. Carefully read the chat messages about what exactly "
    "he is asking you to add at the moment. If you make a mistake, add the wrong file, or add files out of order "
    "as requested by the bot, you will either have to add it again or go to the tour editor if you added a tour. "
    "Either way, if you did make a mistake and the bot froze, click on the menu to the right of the text input box and click /start.\n\n"
    "'Update tour codes' -- This function will automatically update tour codes and delete all tour files from users. "
    "You can check the new codes in the 'Tour list' window. Recommendation: update the codes after each tour. "
    "The bot has a time limit for storing message IDs. The function does not work instantly, so be patient when resetting the codes."
    "It may take two or three minutes.\n\n"
    "'Change admin code' -- You can change the admin code in this window manually. Don't lose it! "
    "Only the bot developer can restore this code.\n\n"
    "For any questions that arise, as well as in case of recommendations for improving the functionality or text accompaniment of the bot, "
    "contact the developer, the link to whose profile is posted in the main admin menu. Good luck!"
    ),
    "russian": (
        "Итак, в меню существует 6 кнопок.\n\n"
        "'Выход' -- отправит вас в окно выбора языка.\n\n"
        "'Инструкция' -- открывает инструкцию, которую вы читаете сейчас.\n\n"
        "'Список экскурсий' -- отправит вас в окно, где на кнопках вы увидите уже добавленные экскурсии с их кодами. Кликнув " 
        "на кнопку с названием экскурсии (если экскурсия существует на русском языке, название её на кнопке автоматически выводится "
        "на русском) вы  выведете полную экскурсию на всех добавленных языках, после чего появятся кнопки 'Удалить' и 'Изменить'. "
        "кнопка 'Удалить' -- после подтверждения - сотрёт экскурсию из базы данных. 'Изменить' -- переведёт вас в меню редактора. "
        "Вы сможете добавить новый язык для экскурсии (если не все из русского, английского и испанского уже добавлены) или править "
        "экскурсию на выбранном языке, на котором тур уже существует. Если вы выбираете правку экскурсии -- вам будет доступно меню "
        "полного редактора названия, описания и отдельно каждого блока экскурсии. Вы также сможете удалить экскурсию на данном языке, "
        "а также добавить или удалить экскурсионный блок. Пожалуйста, внимательно читайте указания бота и "
        "используйте кнопки, если только бот не запрашивает обратного. Обычно, запрос подобного рода содержит слово 'Введите'.\n\n"
        "'Добавить тур' -- Это функция добавления экскурсии. Вы будете последовательно добавлять код, язык, название экскурсии (на данном языке), "
        "описание экскурсии (на данном языке), короткое название для блока экскурсии, аудио (если требуется), фото (если требуется),"
        "порядковый номер блока экскурсии (Пожалуйста, очень внимательно добавляйте порядковый номер блока. Всегда начинайте с единицы и "
        "при добавлении каждого следующего блока идите по возрастанию на единицу [1, 2, 3 ...], пока не закончите добавлять тур на данном языке. "
        "При добавлении нового языка экскурсии, начинайте нумеровать сначала по той же схеме. Соблюдайте соответствие порядка блоков экскурсии " 
        "между языками. Порядковый номер не только отвечает за сортировку блоков экскурсии внутри языка, но и выводится на кнопках выбора конкретной"
        " точки у клиентов) и "
        "описание блока. Пожалуйста, будьте очень внимательны, когда добавляете экскурсию. Внимательно читайте сообщения чата о том, что конкретно "
        "в данный момент он просит вас добавить. Если вы допустите ошибку, добавите неверный файл или добавите файлы не в том порядке, "
        "в котором их запрашивает бот, вам либо придётся добавлять её заново, либо переходить в редактор экскурсий, если вы добавили тур. "
        "Так или иначе, если вы всё-таки совершили ошибку и бот завис, нажмите на меню справа от окна ввода текста, и кликните на /start.\n\n"
        "'Обновить коды экскурсий' -- Эта функция автоматически обновит коды экскурсий и удалит все файлы экскурсий у пользователей. "
        "Проверить новые коды вы сможете в окне 'Список экскурсии'. Рекомендация: обновляйте коды после каждой экскурсии. "
        "У бота есть ограничение по времени хранения ID сообщений. Функция работает не мгновенно, так что ресетя коды, запаситесь терпением."
        "Она может занять две-три минуты.\n\n"
        "'Смена админского кода' -- Вы сможете поменять админский код в этом окне вручную. Не потеряйте его! "
        "Восстановить этот код сможет только разработчик бота.\n\n"
        "По всем возникшим вопросам, а также в случае рекомендаций по улучшению функционала или текстового сопровождения бота, "
        "обращайтесь к разработчику, ссылка на профиль которого выложена в главном админском меню. Желаю удачи!"
    )
}
    
    bot.send_message(
        message.chat.id,
        text=instructions_text.get(lang, instructions_text["english"]),
        reply_markup=markup
    )


# Обработчик возврата к выбору языка или ввода кода
@bot.message_handler(content_types=['text'], func=lambda message: user_state.get(message.chat.id) in (NOACT, START))
def handle_return_to_language_selection(message):
    global user_state
    if message.text in ("Вернуться к выбору языка", "Return to language selection", "Volver a la selección de idioma", "Выход", 
                        "Exit", "Salida", "Volver al menú principal", "Return to main menu", "Вернуться в главное меню"):
        start(message)
    
    elif message.text in ["Инструкция", "Instruction", "Instruccion"]:
        instruction(message)

    elif message.text in ["Volver a la ventana de control", "Return to the control window", "Вернуться в окно управления"]:
        admin_pannel(message)   

    elif message.text in all_excursions[message.chat.id]:
        add_message_id(message.chat.id, message.message_id)
        main_excursion(message)

    elif message.text == adm_code:
        main_admin(message)

    elif message.text in ("Return to entering code", "Вернуться к введению кода", "Volver a la entrada de código"):
        enter_code(message)

    elif code_entering[message.chat.id] == 1:
        # Если код неверен
        if language[message.chat.id] == "spanish":
            bot.send_message(message.chat.id, text="Lo sentimos, pero el código es incorrecto. Si no lo conoces, pregunta al Guía.")
        elif language[message.chat.id] == "english":
            bot.send_message(message.chat.id, text="Sorry, but the code is incorrect. If you don't know it, ask the Guide.")
        elif language[message.chat.id] == "russian":
            bot.send_message(message.chat.id, text="Извините, но код неверен. Если он вам не известен, спросите у гида!")
        enter_code_repeat(message)

    elif message.text in ("Ir al recorrido", "Go to the tour", "Перейти к экскурсии", "Volver al menú del recorrido", "Return to the tour menu", "Вернуться в меню экскурсии"):
        add_message_id(message.chat.id, message.message_id)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            pref = "Descripción del tour"
            nmess0 = bot.send_message(message.chat.id, text = f"{pref}:\n{all_excursions[message.chat.id].get('description')}")
            add_message_id(message.chat.id, nmess0.message_id)
            button1 = types.KeyboardButton("Iniciar el recorrido desde el principio")
            button2 = types.KeyboardButton("Seleccionar un punto específico")
            button3 = types.KeyboardButton("Volver al menú principal")
            markup.row(button1)
            markup.row(button2)
            markup.row(button3)
            nmess = bot.send_message(message.chat.id, text="Si deseas comenzar nuestro recorrido desde el principio, haz clic en el botón 'Iniciar el recorrido desde el principio'. Si ya estás en un punto determinado (por ejemplo, en el monumento a Evita Perón), haz clic en el botón 'Seleccionar un punto específico'", reply_markup=markup)
        elif language[message.chat.id] == "english":
            pref = "Tour description"
            nmess0 = bot.send_message(message.chat.id, text = f"{pref}:\n{all_excursions[message.chat.id].get('description')}")
            add_message_id(message.chat.id, nmess0.message_id)
            button1 = types.KeyboardButton("Start the tour from the beginning")
            button2 = types.KeyboardButton("Select a specific point")
            button3 = types.KeyboardButton("Return to main menu")
            markup.row(button1)
            markup.row(button2)
            markup.row(button3)
            nmess = bot.send_message(message.chat.id, text="If you want to start our tour from the beginning, click on the button 'Start the tour from the beginning'. If you are already at a certain point (for example, at the Evita Peron monument), click on the button 'Select a specific point'", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            pref = "Описание тура"
            nmess0 = bot.send_message(message.chat.id, text = f"{pref}:\n{all_excursions[message.chat.id].get('description')}")
            add_message_id(message.chat.id, nmess0.message_id)
            button1 = types.KeyboardButton("Начать экскурсию сначала")
            button2 = types.KeyboardButton("Выбрать конкретную точку")
            button3 = types.KeyboardButton("Вернуться в главное меню")
            markup.row(button1)
            markup.row(button2)
            markup.row(button3)
            nmess = bot.send_message(message.chat.id, text="Если вы хотите начать наше путешествие сначала, нажмите на кнопку «Начать экскурсию сначала». Если вы находитесь уже в определённой точке (например, у памятника Эвиты Перон), нажмите кнопку «Выбрать конкретную точку»", reply_markup=markup)
        add_message_id(message.chat.id, nmess.message_id)

    elif message.text in ("Iniciar el recorrido desde el principio", "Start the tour from the beginning", "Начать экскурсию сначала"):
        add_message_id(message.chat.id, message.message_id)
        full_tour(message)

    elif message.text in ("Seleccionar un punto específico", "Select a specific point", "Выбрать конкретную точку"):
        add_message_id(message.chat.id, message.message_id)
        partial_tour(message)

    elif message.text in ("Lista de excursiones", "List of tours", "Список экскурсий"):
        view_blocks(message)   

    elif message.text in ("Agregar un recorrido", "Add a tour", "Добавить тур"):
        if language[message.chat.id] == "spanish":
            bot.send_message(message.chat.id, text="Introduce el código para una nueva excursión: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(message.chat.id, text="Enter the code for a new tour: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(message.chat.id, text="Введите код для новой экскурсии: ", reply_markup=types.ReplyKeyboardRemove())	
        user_state[message.chat.id] = ADD_BLOCK_CODE

    elif message.text in ("Cambiar el código de administrador", "Edit the admin code", "Смена админского кода"):
        admin_code_setup(message)
    elif message.text in ("Обновить коды экскурсий", "Update tour codes", "Actualizar códigos de tour"):
        tour_codes(message)

def tour_codes(message):
    if language[message.chat.id] == "spanish":
        b1 = "Continuar"
        b2 = "Volver"
        text = "¿Está seguro de que desea cambiar todos los códigos de viaje existentes?"
    elif language[message.chat.id] == "english":
        b1 = "Continue"
        b2 = "Back"
        text = "Are you sure you want to change all codes for existing tours?"
    elif language[message.chat.id] == "russian":
        b1 = "Продолжить"
        b2 = "Назад"
        text = "Вы действительно хотите изменить все коды существующих туров?"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button1 = types.KeyboardButton(b1)
    button2 = types.KeyboardButton(b2)
    markup.row(button1, button2)
    bot.send_message(message.chat.id, text=text, reply_markup=markup)
    user_state[message.chat.id] = TOUR_CODE

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == TOUR_CODE)
def tour_code_new(message):
    global user_state
    if message.text in ["Volver", "Back", "Назад"]:
        user_state[message.chat.id] = START
        admin_pannel(message)
        return
    if language[message.chat.id] == "spanish":
        text2 = "Se ha iniciado el proceso de actualización de códigos y eliminación de mensajes relacionados con excursiones de los chats de los usuarios. Esto puede tardar unos minutos. Espere la notificación de que todos los códigos se han actualizado y no realice ninguna acción en el bot."
        text = "¡Todos los códigos se actualizaron correctamente y se borraron los historiales de chat de los usuarios!"
    elif language[message.chat.id] == "english":
        text2 = "The process of updating codes and deleting messages related to excursions from user chats has started. This may take several minutes. Please wait for the notification that all codes have been updated and do not perform any actions in the bot."
        text = "All codes have been successfully updated and user's chat histories have been cleared!"
    elif language[message.chat.id] == "russian":
        text2 = "Запущен процесс обновления кодов и удаления сообщений, связанных с экскурсиями из пользовательских чатов. Это может занять несколько минут. Пожалуйста, дождитесь оповещения, что все коды обновлены и не совершайте действий в боте."
        text = "Все коды успешно обновлены, а истории чатов пользователей очищены!"

    bot.send_message(message.chat.id, text=text2, reply_markup=types.ReplyKeyboardRemove())
    reset_all_codes()
    delete_messages()
    clear_message_ids_file()
    bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
    user_state[message.chat.id] = START
    admin_pannel(message)

def admin_code_setup(message):
    global adm_code, user_state
    if language[message.chat.id] == "spanish":
        bot.send_message(message.chat.id, text=f"El código de administrador actual es: {adm_code}")
        b1 = "Continuar"
        b2 = "Volver"
        text = "¿Estás seguro de que deseas cambiar el código de administrador?"
    elif language[message.chat.id] == "english":
        bot.send_message(message.chat.id, text=f"Current admin code is: {adm_code}")
        b1 = "Continue"
        b2 = "Back"
        text = "Are you sure that you want to change the admin code?"
    elif language[message.chat.id] == "russian":
        bot.send_message(message.chat.id, text=f"Текущий админский код: {adm_code}")
        b1 = "Продолжить"
        b2 = "Назад"
        text = "Вы действительно хотите поменять админский код?"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button1 = types.KeyboardButton(b1)
    button2 = types.KeyboardButton(b2)
    markup.row(button1, button2)
    bot.send_message(message.chat.id, text=text, reply_markup=markup)
    user_state[message.chat.id] = ADDMIN_CODE

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == ADDMIN_CODE)
def admin_code_new(message):
    global adm_code, user_state, code_entering
    if message.text in ["Volver", "Back", "Назад"]:
        user_state[message.chat.id] = START
        admin_pannel(message)
        return
    code_entering[message.chat.id] = 1
    if language[message.chat.id] == "spanish":
        text = "Introduzca el nuevo código de administrador. Se recomienda utilizar solo dígitos y que el código tenga una longitud de 6 dígitos."
    elif language[message.chat.id] == "english":
        text = "Enter new admin code. It is recommended to use digits only and code length is 6"
    elif language[message.chat.id] == "russian":
        text = "Введите новый код администратора. Рекомендуется использовать только цифры, длина кода — 6"
    bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
    user_state[message.chat.id] = ADDMIN_CODE_SAVE

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == ADDMIN_CODE_SAVE)
def admin_code_save(message):
    global adm_code, user_state, code_entering
    code_entering[message.chat.id] = 0
    new_code = message.text
    if 6 <= len(new_code.strip()) <= 10:
        adm_code = new_code.strip()
        save_admin_code(adm_code) 
        if language[message.chat.id] == "spanish":
            bot.send_message(message.chat.id, text="¡El código de administrador se ha cambiado correctamente!")
        elif language[message.chat.id] == "english":
            bot.send_message(message.chat.id, text="Admin code has been successfully changed!")
        elif language[message.chat.id] == "russian":
            bot.send_message(message.chat.id, text="Админский код был успешно изменен!")
        user_state[message.chat.id] = START
        admin_pannel(message)
    else:
        if language[message.chat.id] == "spanish":
            bot.send_message(message.chat.id, text="Elija un formato de código diferente. La longitud no debe ser superior a 10 ni inferior a 6.")
        elif language[message.chat.id] == "english":
            bot.send_message(message.chat.id, text="Please choose another code format. The length must be no more than 10 and no less than 6.")
        elif language[message.chat.id] == "russian":
            bot.send_message(message.chat.id, text="Пожалуйста, выберите другой формат кода. Длина должна быть не больше 10 и не меньше 6.")
        user_state[message.chat.id] = ADDMIN_CODE
        admin_code_new(message)

#--------------------ADD NEW TOUR-------------------------------
@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == ADD_BLOCK_CODE)
def add_block_code(message):
    global user_data, user_state
    if message.text in all_excursions[message.chat.id]:
        if language[message.chat.id] == "spanish":
            bot.send_message(message.chat.id, text="Me temo que ya existe un recorrido con este código.")
        elif language[message.chat.id] == "english":
            bot.send_message(message.chat.id, text="I'm afraid a tour with this code already exists.")
        elif language[message.chat.id] == "russian":
            bot.send_message(message.chat.id, text="Боюсь, тур с таким кодом уже существует.")
        user_state[message.chat.id] = START
        admin_pannel(message)
        return
    user_data = getattr(bot, 'user_data', {})
    user_data[message.chat.id] = {'block_code': message.text, 'languages': {}}

    bot.user_data = user_data
    choose_language(message)

def choose_language(message):
    global user_state
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    if language[message.chat.id] == "spanish":
        markup.row("Ruso", "Inglés", "Español")
        markup.row("Terminar de agregar")
        bot.send_message(message.chat.id, text="Seleccionar idioma de audio y descripción: ", reply_markup=markup)
    elif language[message.chat.id] == "english":
        markup.row("Russian", "English", "Spanish")
        markup.row("Finish adding")
        bot.send_message(message.chat.id, text="Select audio and description language: ", reply_markup=markup)
    elif language[message.chat.id] == "russian":
        markup.row("Русский", "Английский", "Испанский")
        markup.row("Завершить добавление")
        bot.send_message(message.chat.id, text="Выберите язык аудио и описания: ", reply_markup=markup)
    user_state[message.chat.id] = CHOOSE_LANGUAGE

@bot.message_handler(func=
lambda message: user_state.get(message.chat.id) == CHOOSE_LANGUAGE)
def handle_language_choice(message):

    global user_data, user_state
    user_id = message.chat.id
    if message.text in ["Terminar de agregar", "Finish adding", "Завершить добавление"]:
        save_block(message)
        return
    lang_map = {"Ruso": "Russian", "Inglés": "English", "Español": "Spanish", "Russian": "Russian",
                "English": "English", "Spanish": "Spanish", "Русский": "Russian", "Английский": "English", "Испанский": "Spanish"}
    if message.text in lang_map:
        selected_lang = lang_map[message.text]
        if user_id not in user_data:
            user_data[user_id] = {'block_code': '', 'languages': {}}
        user_data[user_id]['current_language'] = selected_lang
        if 'languages' not in user_data[user_id]:
            user_data[user_id]['languages'] = {}
        if selected_lang not in user_data[user_id]['languages']:
            user_data[user_id]['languages'][selected_lang] = {'name': '', 'description' : '', 'points': {}}
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Introduce el nombre de la excursión: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Enter the name of the excursion: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Введите название экскурсии: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = ADD_BLOCK_NAME
    else:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Seleccione un idioma de las opciones proporcionadas.")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Please select a language from the options provided.")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Пожалуйста, выберите язык из предложенных вариантов.")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == ADD_BLOCK_NAME)
def add_block_name(message):
    global user_data, user_state
    user_id = message.chat.id
    user_data[user_id]['languages'][user_data[user_id]['current_language']]['name'] = message.text
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, text="Por favor introduzca una descripción de la excursión. Se mostrará al cliente en el menú de excursiones.")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, text="Please enter a description of the excursion. It will be displayed to the client in the excursion menu.")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, text="Введите, пожалуйста, описание экскурсии. Оно будет демонстрироваться клиенту в меню экскурсии.")
    user_state[user_id] = ADD_DESCRIPTION_MAIN

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == ADD_DESCRIPTION_MAIN)
def add_description_main(message):
    global user_data, user_state
    user_id = message.chat.id
    user_data[user_id]['languages'][user_data[user_id]['current_language']]['description'] = message.text
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        button1 = types.KeyboardButton("Si")
        button2 = types.KeyboardButton("No")
        markup.row(button1, button2)
        bot.send_message(user_id, text="¿Prefieres el audio?", reply_markup=markup)
    elif language[message.chat.id] == "english":
        button1 = types.KeyboardButton("Yes")
        button2 = types.KeyboardButton("No")
        markup.row(button1, button2)
        bot.send_message(user_id, text="Do we add audio tape?", reply_markup=markup)
    elif language[message.chat.id] == "russian":
        button1 = types.KeyboardButton("Да")
        button2 = types.KeyboardButton("Нет")
        markup.row(button1, button2)
        bot.send_message(user_id, text="Прикрепляем аудиофайл?", reply_markup=markup)
    user_state[user_id] = CONF_AUDIO

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == CONF_AUDIO)
def check_audio_addition(message):
    global user_data, user_state
    user_id = message.chat.id
    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar un archivo de audio: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send an audio file: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Отправьте аудиофайл: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = ADD_AUDIO
    elif message.text in ["Нет", "No"]:
        user_data[user_id]['current_audio_url'] = "No file"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres foto?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add photo?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем фото?", reply_markup=markup)
        user_state[user_id] = CONF_PHOTO

@bot.message_handler(content_types=['audio'], func=lambda message: user_state.get(message.chat.id) == ADD_AUDIO)
def add_audio(message):
    global user_data, user_state
    user_id = message.chat.id
    if user_id not in user_data:
        user_data[user_id] = {}
    try:
        file_info = bot.get_file(message.audio.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        if 'block_code' not in user_data[user_id] or 'current_language' not in user_data[user_id]:
            raise ValueError("Missing block_code or current_language")
        file_name = f"{user_data[user_id]['block_code']}_{user_data[user_id]['current_language']}_{len(user_data[user_id]['languages'][user_data[user_id]['current_language']]['points'])}.mp3"
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='audio/mpeg')
        blob.make_public()
        # Получение URL файла
        audio_url = blob.public_url
        user_data[user_id]['current_audio_url'] = audio_url
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres foto?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add photo?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем фото?", reply_markup=markup)
        user_state[user_id] = CONF_PHOTO
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de audio: {str(e)}")
        logger.error(f"Error processing audio file: {str(e)}")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == CONF_PHOTO)
def check_photo_addition(message):
    global user_data, user_state
    user_id = message.chat.id
    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar una foto: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send photo: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Отправьте фотографию: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = ADD_PHOTO
    elif message.text in ["Нет", "No"]:
        user_data[user_id]['current_photo_url'] = "No file"
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Agregue un nombre corto para el block de tour. Este es el nombre que el cliente verá en el botón: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Add a short name for this excursion block. This name will be seen by the client on the button: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Добавьте короткое имя для данного блока экскурсии. Это имя будет видеть клиент на кнопке: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = SHORT_NAME

@bot.message_handler(content_types=['photo'], func=lambda message: user_state.get(message.chat.id) == ADD_PHOTO)
def add_photo(message):
    global user_data, user_state
    user_id = message.chat.id
    if user_id not in user_data:
        user_data[user_id] = {}
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        if 'block_code' not in user_data[user_id] or 'current_language' not in user_data[user_id]:
            raise ValueError("Missing block_code or current_language")
        file_name = f"{user_data[user_id]['block_code']}_{user_data[user_id]['current_language']}_{len(user_data[user_id]['languages'][user_data[user_id]['current_language']]['points'])}_photo.jpg"
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='image/jpeg')
        blob.make_public()
        # Получение URL файла
        photo_url = blob.public_url
        user_data[user_id]['current_photo_url'] = photo_url
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Foto recibida. Agregue un nombre corto para el block de tour. Este es el nombre que el cliente verá en el botón: ")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Photo received. Add a short name for this excursion block. This name will be seen by the client on the button: ")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Фотография получена. Добавьте короткое имя для данного блока экскурсии. Это имя будет видеть клиент на кнопке: ")
        user_state[user_id] = SHORT_NAME
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de photo: {str(e)}")
        logger.error(f"Error processing photo file: {str(e)}")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == SHORT_NAME)
def add_short_name(message):
    global user_data, user_state
    user_id = message.chat.id
    short_name = message.text
    user_data[user_id]['current_short_name'] = short_name
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, "Nombre corto recibido. Ahora agregue el número de secuencia:")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, "Short name received. Now add the serial number:")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, "Короткое имя получено. Теперь добавьте порядковый номер: ")
    user_state[user_id] = ADD_ORDER

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == ADD_ORDER)
def add_order(message):
    global user_data, user_state
    user_id = message.chat.id
    order = message.text
    user_data[user_id]['order'] = int(order)
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, "Nombre corto recibido. Ahora agrega una descripción")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, "Short name received. Now add a description")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, "Короткое имя получено. Теперь добавьте описание: ")
    user_state[user_id] = ADD_DESCRIPTION

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == ADD_DESCRIPTION)
def add_description(message):
    global user_data, user_state
    user_id = message.chat.id
    description = message.text
    current_lang = user_data[user_id]['current_language']
    short_name = user_data[user_id]['current_short_name']
    order = user_data[user_id]['order']
    user_data[user_id]['languages'][current_lang]['points'][short_name] = {
        'audio': user_data[user_id]['current_audio_url'],
        'photo': user_data[user_id]['current_photo_url'],
        'description': description,
        'order' : order
    }
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        markup.row('Agregar block', 'Seleccionar otro idioma', 'Terminar de agregar')
        bot.send_message(user_id, "Este parte añadido. ¿Qué sigue?", reply_markup=markup)
    elif language[message.chat.id] == "english":
        markup.row('Add block', 'Select another language', 'Finish adding')
        bot.send_message(user_id, "Block added. What's next?", reply_markup=markup)
    elif language[message.chat.id] == "russian":
        markup.row('Добавить блок', 'Выбрать другой язык', 'Завершить добавление')
        bot.send_message(user_id, "Блок добавлен. Что дальше?", reply_markup=markup)
    user_state[user_id] = CONFIRM_AUDIO

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == CONFIRM_AUDIO)
def confirm_audio(message):
    global user_state
    user_id = message.chat.id
    if message.text in ['Добавить блок', 'Add block', 'Agregar block']:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres el audio?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add audio tape?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем аудиофайл?", reply_markup=markup)
        user_state[user_id] = CONF_AUDIO
    elif message.text in ['Выбрать другой язык', 'Select another language', 'Seleccionar otro idioma']:
        choose_language(message)
    elif message.text in ['Завершить добавление', 'Finish adding', 'Terminar de agregar']:
        save_block(message)

def save_block(message):
    global user_data, user_state
    user_data = getattr(bot, 'user_data', {}).get(message.chat.id, {})
    block_code = user_data['block_code']
    languages = user_data['languages']
   
    # Сохранение данных в Firebase Realtime Database
    block_ref = database.child('blocks').child(block_code)
    block_ref.set(languages)
    
    # Создание клавиатуры и отправка сообщения о сохранении
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        b1 = types.KeyboardButton("Lista de excursiones")
        b2 = types.KeyboardButton("Agregar un recorrido")
        b3 = types.KeyboardButton("Actualizar códigos de tour")
        b4 = types.KeyboardButton("Cambiar el código de administrador")
        b5 = types.KeyboardButton("Instruccion")
        b6 = types.KeyboardButton("Salida")
        markup.row(b1, b2)
        markup.row(b3, b4)
        markup.row(b5)
        markup.row(b6)
        bot.send_message(
            message.chat.id,
            text="¡Bloque guardado exitosamente!\n"
                 "Esta es la ventana de gestión de excursiones. Para obtener más información sobre las capacidades del administrador, puede hacer clic en el botón 'Instrucciones'\n"
                 "Si tienes alguna otra pregunta, escribe al desarrollador https://t.me/The_lord_of_the_dawn",
            reply_markup=markup
        )
    elif language[message.chat.id] == "english":
        b1 = types.KeyboardButton("List of tours")
        b2 = types.KeyboardButton("Add a tour")
        b3 = types.KeyboardButton("Update tour codes")
        b4 = types.KeyboardButton("Edit the admin code")
        b5 = types.KeyboardButton("Instruction")
        b6 = types.KeyboardButton("Exit")
        markup.row(b1, b2)
        markup.row(b3, b4)
        markup.row(b5)
        markup.row(b6)
        bot.send_message(
            message.chat.id,
            text="Block saved successfully!\n"
                 "This is the excursion management window. To learn more about the admin's capabilities, you can click on the 'Instructions' button\n"
                 "If you have any other questions, write to the developer https://t.me/The_lord_of_the_dawn",
            reply_markup=markup
        )
    elif language[message.chat.id] == "russian":
        b1 = types.KeyboardButton("Список экскурсий")
        b2 = types.KeyboardButton("Добавить тур")
        b3 = types.KeyboardButton("Обновить коды экскурсий")
        b4 = types.KeyboardButton("Смена админского кода")
        b5 = types.KeyboardButton("Инструкция")
        b6 = types.KeyboardButton("Выход")
        markup.row(b1, b2)
        markup.row(b3, b4)
        markup.row(b5)
        markup.row(b6)
        bot.send_message(
            message.chat.id,
            text="Блок успешно сохранен!\n"
                 "Это окно управления экскурсиями. Чтобы узнать подробнее о возможностях админа, вы можете кликнуть на кнопку 'Инструкция'\n"
                 "Если есть другие вопросы, пишите разработчику https://t.me/The_lord_of_the_dawn",
            reply_markup=markup
        )
    # Обновление состояния пользователя и очистка данных
    user_state[message.chat.id] = START
    bot.user_data = getattr(bot, 'user_data', {})
    bot.user_data[message.chat.id] = {}

def view_blocks(message):
    global user_state, block_name
    blocks = database.child('blocks').get()
    block_name[message.chat.id] = ""
    if not blocks:
        if language[message.chat.id] == "spanish":
            bot.send_message(message.chat.id, "Aún no hay bloques.")
        elif language[message.chat.id] == "english":
            bot.send_message(message.chat.id, "There are no blocks yet.")
        elif language[message.chat.id] == "russian":
            bot.send_message(message.chat.id, "Блоков пока нет.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for block_code in blocks:
        if 'Russian' in blocks[block_code]:
            ex_name = blocks[block_code]['Russian']['name']
        elif 'English' in blocks[block_code]:
            ex_name = blocks[block_code]['English']['name']
        elif 'Spanish' in blocks[block_code]:
            ex_name = blocks[block_code]['Spanish']['name']
        markup.add(f"{ex_name} (Code: {block_code})")

    if language[message.chat.id] == "spanish":
        markup.add('Atrás')
        bot.send_message(message.chat.id, 'Todas las excursiones agregadas se presentan aquí. Pulsa sobre el nombre de la excursión para visualizarla, así como eliminarla o cambiarla.', reply_markup=markup)
    elif language[message.chat.id] == "english":
        markup.add('Back')
        bot.send_message(message.chat.id, 'All added excursions are presented here. Click on the excursion name to display it, as well as delete or change it.', reply_markup=markup)
    elif language[message.chat.id] == "russian":
        markup.add('Назад')
        bot.send_message(message.chat.id, 'Здесь представлены все добавленные экскурсии. Кликните на название экскурсии, чтобы вывесте её, а так же удалить или изменить.', reply_markup=markup)
    user_state[message.chat.id] = 'VIEW_BLOCKS'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'VIEW_BLOCKS')
def handle_block_selection(message):
    global block_name, user_state
    if message.text in ['Назад', 'Back', 'Atrás']:
        admin_pannel(message)
        return
    trt = message.text
    mess = trt.split(" (Code:")[0]
    # Установка языковых переменных
    if language[message.chat.id] == "spanish":
        block = "Recorrido"
        text = "Seleccionar acción:"
        chg = "Cambiar"
        dlt = "Eliminar"
        bck = "Atrás"
        ord_ex = "Orden"
        shrt_ex = "Nombre corto"
        lang_ex = "Idioma"
        name_ex = "Nombre"
        code_ex = "Código"
        descr_ex = "Descripción"
    elif language[message.chat.id] == "english":
        block = "Tour"
        text = "Select action:"
        chg = "Edit"
        dlt = "Delete"
        bck = "Back"
        ord_ex = "Order"
        shrt_ex = "Short name"
        lang_ex = "Language"
        name_ex = "Name"
        code_ex = "Code"
        descr_ex = "Description"
    elif language[message.chat.id] == "russian":
        block = "Тур"
        text = "Выберите действие:"
        chg = "Изменить"
        dlt = "Удалить"
        bck = "Назад"
        ord_ex = "Порядок"
        shrt_ex = "Короткое имя"
        lang_ex = "Язык"
        name_ex = "Название"
        code_ex = "Код"
        descr_ex = "Описание"
    # Получение блоков из базы данных
    languages = ['Russian', 'English', 'Spanish']
    blocks = database.child('blocks').get()
    block_name[message.chat.id] = mess
    # Поиск блока с выбранным именем
    code = None
    for block_code, block_data in blocks.items():
        for lang in languages:
            if lang in block_data and block_data[lang].get('name') == mess:
                code = block_code
                break

    if not code:
        # Отправка сообщения, если блок не найден
        not_found_message = {
            "spanish": "Bloque no encontrado.",
            "english": "Block not found.",
            "russian": "Блок не найден."
        }
        bot.send_message(message.chat.id, not_found_message.get(language[message.chat.id], "Block not found"))
        return

    # Получение данных конкретного блока по коду
    block_data = database.child('blocks').child(code).get()
    
    if block_data:
        # Проходим по каждому языковому разделу
        for lang, content in block_data.items():
            # Отправляем сообщение с языком, названием и кодом блока
            bot.send_message(message.chat.id, f"{lang_ex}: {lang}, \n{name_ex}: {content.get('name')}, \n{code_ex}: {code}, \n{descr_ex}: {content.get('description')}")

            # Получаем точки и отправляем информацию по каждой точке отдельным сообщением
            points = content.get('points', {})
            points = dict(sorted(
                points.items(),
                key=lambda item: item[1]['order']
                )
            )
            for point_name, details in points.items():
                description = details.get('description', 'Описание отсутствует')
                photo_url = details.get('photo')
                audio_url = details.get('audio')
                order = details.get('order')
                # Отправляем фото, если оно есть и доступно
                if photo_url:
                    if photo_url == "No file":
                        bot.send_message(message.chat.id, text=f"{ord_ex}: {order}\n{shrt_ex}: {point_name}\n{descr_ex}: {description}")
                    else:
                        try:
                            response = requests.get(photo_url)
                            if response.status_code == 200:
                                bot.send_photo(message.chat.id, photo_url, caption=f"{ord_ex}: {order}\n{shrt_ex}: {point_name}\n{descr_ex}: {description}")
                            else:
                                bot.send_message(message.chat.id, "Фото не удалось загрузить.")
                        except requests.exceptions.RequestException:
                            bot.send_message(message.chat.id, "Ошибка загрузки фото.")

                # Отправляем аудио, если оно есть и доступно
                if audio_url:
                    if audio_url != "No file":
                        try:
                            response = requests.get(audio_url)
                            if response.status_code == 200:
                                bot.send_audio(message.chat.id, audio_url)
                            else:
                                bot.send_message(message.chat.id, "Аудио не удалось загрузить.")
                        except requests.exceptions.RequestException:
                            bot.send_message(message.chat.id, "Ошибка загрузки аудио.")
                bot.send_message(message.chat.id, "----------------------")
                    
        # Добавляем кнопки для редактирования, удаления или возврата
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(chg, dlt)
        markup.row(bck)
        bot.send_message(message.chat.id, text=text, reply_markup=markup)
        user_state[message.chat.id] = 'BLOCK_ACTION'
    else:
        # Сообщение об отсутствии данных для блока
        not_found_message = {
            "spanish": "Bloque no encontrado.",
            "english": "Block not found.",
            "russian": "Блок не найден."
        }
        bot.send_message(message.chat.id, not_found_message.get(language[message.chat.id], "Block not found"))

@bot.message_handler(func=lambda message: user_state[message.chat.id] == 'BLOCK_ACTION')
def handle_block_action(message):
    if message.text in ['Назад', 'Back', 'Atrás']:
        view_blocks(message)
        return
    global user_state
    if language[message.chat.id] == "spanish":
        y = "Sí"
        add_lang = "Agregar idioma del recorrido"
        mod_lang = "Seleccione el idioma del recorrido para editar"
        bck = "Atrás"
        text_del = "¿Estás seguro de que deseas eliminar este recorrido por completo? La acción no se puede deshacer."
        text_ed = "Esta es la ventana de ediciones. Aquí puede agregar un nuevo idioma para el recorrido o seleccionar el idioma existente del recorrido actual en el que el recorrido requiere edición."
    elif language[message.chat.id] == "english":
        y = "Yes"
        add_lang = "Add tour language"
        mod_lang = "Select the tour language for editing"
        bck = "Back"
        text_del = "Are you sure you want to delete this tour completely? The action cannot be undone."
        text_ed = "This is the edit window. Here you can add a new tour language, or select an existing tour language, in which the tour requires editing."
    elif language[message.chat.id] == "russian":
        y = "Да"
        add_lang = "Добавить язык тура"
        mod_lang = "Выбрать язык тура для правки"
        bck = "Назад"
        text_del = "Вы действительно хотите полностью удалить этот тур? Действие нельзя будет отменить."
        text_ed = "Это окно правок. Здесь вы можете добавить новый язык экскурсии, или выбрать существующий язык текущий экскурсии, на котором тур требует правки."

    if message.text in ["Удалить", "Delete", "Eliminar"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(y, bck)
        bot.send_message(message.chat.id, text_del, reply_markup=markup)
        user_state[message.chat.id] = 'BLOCK_REMOVE'
    elif message.text in ["Изменить", "Edit", "Cambiar"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(add_lang)
        markup.row(mod_lang)
        markup.row(bck)
        bot.send_message(message.chat.id, text_ed, reply_markup=markup)
        user_state[message.chat.id] = 'BLOCK_EDIT'

@bot.message_handler(func=lambda message: user_state[message.chat.id] == 'BLOCK_REMOVE')
def handle_block_action(message):
    if message.text in ['Назад', 'Back', 'Atrás']:
        view_blocks(message)
        return
    
    global block_name, user_state
    if language[message.chat.id] == "spanish":
        block = "Recorrido"
        bck = "Atrás"
        text1 = "fue eliminado exitosamente de la base de datos."
    elif language[message.chat.id] == "english":
        block = "Tour"
        bck = "Back"
        text1 = "was successfully removed from database."
    elif language[message.chat.id] == "russian":
        block = "Тур"
        bck = "Назад"
        text1 = "успешно удален из базы данных."
    # Получение блоков из базы данных
    languages = ['Russian', 'English', 'Spanish']
    blocks = database.child('blocks').get()
    
    # Поиск блока с выбранным именем
    code = None
    for block_code, block_data in blocks.items():
        for lang in languages:
            if lang in block_data and block_data[lang].get('name') == block_name[message.chat.id]:
                code = block_code
                break

    # Получение данных конкретного блока по коду
    block_data = database.child('blocks').child(code).get()
    if block_data:
        try:
            # Удаляем блок из Firebase Realtime Database
            database.child('blocks').child(code).delete()
            bot.send_message(message.chat.id, f"{block} {block_name[message.chat.id]} {text1}")
            block_name[message.chat.id] = ""
            user_state[message.chat.id] = START
            view_blocks(message)
        except Exception as e:
            bot.send_message(message.chat.id, f"ERROR: Ошибка при удалении блока: {str(e)}")
    else:
        bot.send_message(message.chat.id, "ERROR: Не удалось определить код блока для удаления.")
    
# Функция для обработки основного окна экскурсии
def main_excursion(message):
    global code_entering, all_excursions
    code_entering[message.chat.id] = 0
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    all_excursions[message.chat.id] = database.child('blocks').child(message.text).get()
    enter_lang = 0
    langs = 0
    text = ""
    if all_excursions[message.chat.id]:
        # Проходим по каждому языковому разделу
        for lang_tuple in all_excursions[message.chat.id].items():
            lang = lang_tuple[0] if isinstance(lang_tuple, tuple) else lang_tuple
            if lang.lower() == language[message.chat.id]:
                enter_lang = 1
                if language[message.chat.id] == "spanish":
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['Spanish']
                    button1 = types.KeyboardButton("Volver a la selección de idioma")
                    button2 = types.KeyboardButton("Ir al recorrido")
                    text = "Ha ingresado exitosamente a la ventana del recorrido inicial. Para continuar, utilice los botones en la parte inferior de la pantalla."
                elif language[message.chat.id] == "english":
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['English']
                    button1 = types.KeyboardButton("Return to language selection")
                    button2 = types.KeyboardButton("Go to the tour")
                    text = "You have successfully entered the initial tour window. To continue, use the buttons at the bottom of the screen."
                elif language[message.chat.id] == "russian":
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['Russian']
                    button1 = types.KeyboardButton("Вернуться к выбору языка")
                    button2 = types.KeyboardButton("Перейти к экскурсии")
                    text = "Вы успешно вошли в начальное окно тура. Чтобы продолжить, используйте кнопки внизу экрана."
                markup.row(button2)
                markup.row(button1)
                bot.send_message(message.chat.id, text=text, reply_markup=markup)
            else:
                if lang == "English":
                    langs = 2
                    break
                elif lang == "Spanish":
                    langs = 1

        if enter_lang == 0:
            if language[message.chat.id] == "spanish":
                button1 = types.KeyboardButton("Volver a la selección de idioma")
                button2 = types.KeyboardButton("Ir al recorrido")
                if langs == 2:
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['English']
                    text ="Lo sentimos, pero parece que tu recorrido no está disponible en tu idioma. Te redirigiremos automáticamente al inglés. Si tiene alguna pregunta, comuníquese con su guía. Para continuar, utilice los botones en la parte inferior de la pantalla.\n¡Le pedimos disculpas!"
                elif langs == 0:
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['Russian']
                    text ="Lo sentimos, pero parece que tu recorrido no está disponible en tu idioma. Te redirigiremos automáticamente al ruso. Si tiene alguna pregunta, comuníquese con su guía. Para continuar, utilice los botones en la parte inferior de la pantalla.\n¡Le pedimos disculpas!"
            elif language[message.chat.id] == "english":
                button1 = types.KeyboardButton("Return to language selection")
                button2 = types.KeyboardButton("Go to the tour")
                if langs == 1:
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['Spanish']
                    text = "We're sorry, but it looks like your tour is not available in your language. We'll automatically redirect you to Spanish. For any questions, please contact your tour guide. To continue, use the buttons at the bottom of the screen.\nWe apologize!"
                elif langs == 0:
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['Russian']
                    text = "We are sorry, but it seems that your tour is not available in your language. We will automatically redirect you to Russian. For any questions, please contact the guide. To continue, use the buttons at the bottom of the screen.\nWe apologize!"
            elif language[message.chat.id] == "russian":
                button1 = types.KeyboardButton("Вернуться к выбору языка")
                button2 = types.KeyboardButton("Перейти к экскурсии")
                if langs == 2:
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['English']
                    text = "Сожалеем, но похоже ваш тур не доступен на вашем языке. Мы автоматически перенаправляем вас на английский язык. По всем вопросам, пожалуйста, обращайтесь к гиду. Чтобы продолжить, используйте кнопки внизу экрана.\nПриносим свои извинения!"
                elif langs == 1:
                    all_excursions[message.chat.id] = all_excursions[message.chat.id]['Spanish']
                    text = "Сожалеем, но похоже ваш тур не доступен на вашем языке. Мы автоматически перенаправляем вас на испанский язык. По всем вопросам, пожалуйста, обращайтесь к гиду. Чтобы продолжить, используйте кнопки внизу экрана.\nПриносим свои извинения!"
            markup.row(button2)
            markup.row(button1)
            nmes = bot.send_message(message.chat.id, text=text, reply_markup=markup)
            add_message_id(message.chat.id, nmes.message_id)

#----------------------FULL TOUR---------------------------------
# Хранение текущего индекса поинта для каждого пользователя
# Глобальная переменная для отслеживания текущего индекса поинта для каждого пользователя
current_point_index = {}
cur_ex_ind = {}
def get_language_variables(chat_id):
    if language[chat_id] == "spanish":
        return {
            "name": "Nombre del recorrido",
            "descrout": "No hay descripción disponible",
            "descr": "Descripción",
            "photoMis": "La foto no se pudo cargar.",
            "photoErr": "Error al cargar la foto.",
            "audioMis": "Error al cargar el audio.",
            "audioErr": "Error al cargar audio.",
            "text": "Haga clic en 'Siguiente' para continuar",
            "text_end": "Has llegado al final del recorrido",
            "button_text_next": "Siguiente",
            "button_text_back": "Volver al menú del recorrido",
            "take_end" : "Se ha llegado al final de la excursión.",
            "finish" : "Volver"
        }
    elif language[chat_id] == "english":
        return {
            "name": "Tour name",
            "descrout": "No description",
            "descr": "Description",
            "photoMis": "Photo failed to load.",
            "photoErr": "Error loading photo.",
            "audioMis": "Audio failed to load.",
            "audioErr": "Error loading audio.",
            "text": "Click 'Next' to continue",
            "text_end": "You have reached the end of the tour",
            "button_text_next": "Next",
            "button_text_back": "Return to the tour menu",
            "take_end" : "The end of the tour has been reached.",
            "finish" : "Back"
        }
    else:
        return {
            "name": "Название экскурсии",
            "descrout": "Описание отсутствует",
            "descr": "Описание",
            "photoMis": "Фото не удалось загрузить.",
            "photoErr": "Ошибка загрузки фото.",
            "audioMis": "Аудио не удалось загрузить.",
            "audioErr": "Ошибка загрузки аудио.",
            "text": "Нажмите 'Далее' чтобы продолжить",
            "text_end": "Вы достигли конца тура",
            "button_text_next": "Далее",
            "button_text_back": "Вернуться в меню экскурсии",
            "take_end" : "Достигнут конец экскурсии.",
            "finish" : "Назад"
        }

# Основная функция для начала экскурсии
def full_tour(message):
    global current_point_index, user_state
    chat_id = message.chat.id
    add_message_id(chat_id, message.message_id)
    global code_entering
    code_entering[chat_id] = 0
    user_state[chat_id] = 'USER_POINT_FULL_VIEW'  # Устанавливаем состояние пользователя

    lang_vars = get_language_variables(chat_id)

    # Получаем список точек в блоке и сортируем их
    points = all_excursions[chat_id].get('points', {})
    if not points:
        nmess1 = bot.send_message(chat_id, "Нет доступных точек в этой экскурсии.")
        add_message_id(message.chat.id, nmess1.message_id)
        return

    points = dict(sorted(points.items(), key=lambda item: item[1].get('order', 0)))
    current_point_index[chat_id] = 0  # Начинаем с первой точки
    nmess = bot.send_message(chat_id, f"{lang_vars['name']}: {all_excursions[chat_id].get('name', 'Неизвестная экскурсия')}")
    add_message_id(chat_id, nmess.message_id)
    send_point(chat_id, message, points, lang_vars)


def send_point(chat_id, message, points, lang_vars):
    point_keys = list(points.keys())
    add_message_id(chat_id, message.message_id)
    if not point_keys:
        nmes = bot.send_message(chat_id, "Не найдены точки для данного блока.")
        add_message_id(chat_id, nmes.message_id)
        return

    current_index = current_point_index.get(chat_id, 0)
    if current_index >= len(point_keys):
        nmes = bot.send_message(chat_id, lang_vars['take_end'])
        add_message_id(chat_id, nmes.message_id)
        return

    point_name = point_keys[current_index]
    details = points[point_name]
    description = details.get('description', lang_vars['descrout'])
    photo_url = details.get('photo')
    audio_url = details.get('audio')

    # Отправляем фото, если доступно
    if photo_url:
        if photo_url == "No file":
            msg = bot.send_message(chat_id, text=f"{description}")
            add_message_id(chat_id, msg.message_id)
        else:
            try:
                response = requests.get(photo_url)
                if response.status_code == 200:
                    msg = bot.send_photo(chat_id, photo_url, caption=f"{description}")
                else:
                    msg = bot.send_message(chat_id, lang_vars['photoMis'])
            except requests.exceptions.RequestException:
                msg = bot.send_message(chat_id, lang_vars['photoErr'])
            add_message_id(chat_id, msg.message_id)

    # Отправляем аудио, если доступно
    if audio_url:
        if audio_url != "No file":
            try:
                response = requests.get(audio_url)
                if response.status_code == 200:
                    msg = bot.send_audio(chat_id, audio_url)
                else:
                    msg = bot.send_message(chat_id, lang_vars['audioMis'])
            except requests.exceptions.RequestException:
                msg = bot.send_message(chat_id, lang_vars['audioErr'])
            add_message_id(chat_id, msg.message_id)

    # Клавиатура с кнопками навигации
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if current_index < len(point_keys) - 1:
        button_next = types.KeyboardButton(lang_vars['button_text_next'])
        text = lang_vars['text']
        markup.add(button_next)
    else:
        text = lang_vars['text_end']
    button_back = types.KeyboardButton(lang_vars['button_text_back'])
    markup.add(button_back)

    # Отправляем сообщение с кнопками
    msg = bot.send_message(chat_id, text, reply_markup=markup)
    add_message_id(chat_id, msg.message_id)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'USER_POINT_FULL_VIEW')
def handle_navigation(message):
    global user_state, current_point_index
    chat_id = message.chat.id
    lang_vars = get_language_variables(chat_id)
    points = all_excursions[chat_id].get('points', {})
    points = dict(sorted(points.items(), key=lambda item: item[1].get('order', 0)))

    if message.text in [lang_vars['button_text_next']]:
        # Проверяем, не достигнут ли конец списка
        if current_point_index[chat_id] < len(points) - 1:
            current_point_index[chat_id] += 1
            send_point(chat_id, message, points, lang_vars)
        else:
            nmess = bot.send_message(chat_id, lang_vars['take_end'])
            add_message_id(chat_id, nmess.message_id)
    elif message.text in [lang_vars['button_text_back']]:
        # Возвращаемся к началу экскурсии
        add_message_id(chat_id, message.message_id)
        user_state[message.chat.id] = NOACT
        current_point_index[chat_id] = 0
        handle_return_to_language_selection(message)
        return

#----------------------PARTIAL TOUR---------------------------------
button_lst = {}
# Функция для обработки основного окна экскурсии
def partial_tour(message):
    add_message_id(message.chat.id, message.message_id)
    global code_entering, user_state, button_lst, cur_ex_ind
    code_entering[message.chat.id] = 0
    cur_ex_ind[message.chat.id] = 0
    button_lst[message.chat.id] = []
    # Отправляем сообщение с языком, названием и кодом блока
    if language[message.chat.id] == "spanish":
        name = "Nombre del recorrido"
    elif language[message.chat.id] == "english":
        name = "Tour name"
    elif language[message.chat.id] == "russian":
        name = "Название экскурсии"
    nmess = bot.send_message(message.chat.id, f"{name}: {all_excursions[message.chat.id].get('name')}")
    add_message_id(message.chat.id, nmess.message_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    points = all_excursions[message.chat.id].get('points', {})
    points = dict(
    sorted(
        points.items(),
        key=lambda item: item[1]['order']
        )
    )
    for short_name in points:
        print(short_name)
        order = str(points[short_name].get('order'))
        button = types.KeyboardButton(f"{order}. {short_name}")
        markup.add(button)
        button_lst[message.chat.id].append(f"{order}. {short_name}")

    if language[message.chat.id] == "spanish":
        button1 = types.KeyboardButton("Volver al menú del recorrido")
        text = "A continuación te presentamos los principales lugares que puedes visitar como parte de nuestra excursión. ¡Haz clic en el botón con el nombre correspondiente para saber más sobre el lugar especificado!"
    elif language[message.chat.id] == "english":
        button1 = types.KeyboardButton("Return to the tour menu")
        text = "Here are the main places that you can visit during our tour. Click on the button with the corresponding name to learn more about the indicated place!"
    elif language[message.chat.id] == "russian":
        button1 = types.KeyboardButton("Вернуться в меню экскурсии")
        text = "Здесь представлены основные места, которые можно посетить в рамках нашей экскурсии. Кликните на кнопку с соответствующим названием, чтобы узнать об указанном месте подробнее!"
    markup.row(button1)
    nmess = bot.send_message(message.chat.id, text = text, reply_markup=markup)
    add_message_id(message.chat.id, nmess.message_id)
    user_state[message.chat.id] = 'USER_POINT_VIEW'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'USER_POINT_VIEW')
def handle_point_selection(message):
    global user_state, cur_ex_ind
    add_message_id(message.chat.id, message.message_id)
    lang_vars = get_language_variables(message.chat.id)
    pattern = r"^\d+\.\s*(.*)"
    if message.text in [lang_vars['button_text_back']]:
        user_state[message.chat.id] = NOACT
        handle_return_to_language_selection(message)
        cur_ex_ind[message.chat.id] = 0
        return
    elif message.text in button_lst[message.chat.id]:
        mess = re.search(pattern, message.text).group(1)
        points = all_excursions[message.chat.id].get('points', {})
    elif message.text in [lang_vars['button_text_next']]:
        if cur_ex_ind.get(message.chat.id) == 0:
            if language[message.chat.id] == "spanish":
                bot.send_message(message.chat.id, "Por favor use los botones para continuar.")
            elif language[message.chat.id] == "english":
                bot.send_message(message.chat.id, "Please use the buttons to continue.")
            elif language[message.chat.id] == "russian":
                bot.send_message(message.chat.id, "Пожалуйста, используйте кнопки для продолжения.")
            add_message_id(message.chat.id, message.message_id)
            partial_tour(message)
            return
        else:
            points_cur = all_excursions[message.chat.id].get('points', {})
            points_cur = dict(
                sorted(
                    points_cur.items(),
                    key=lambda item: item[1]['order']
                )
            )
            point_keys = list(points_cur.keys())
            i = 0
            mess = ""
            for shnm in point_keys:
                i += 1
                if i == cur_ex_ind[message.chat.id] + 1:
                    mess = shnm
            points = all_excursions[message.chat.id].get('points', {})
            if mess == "":
                user_state[message.chat.id] = NOACT
                handle_return_to_language_selection(message)
                cur_ex_ind[message.chat.id] = 0
                return
    else:
        if language[message.chat.id] == "spanish":
            ms = bot.send_message(message.chat.id, "Por favor use los botones para continuar.")
        elif language[message.chat.id] == "english":
            ms = bot.send_message(message.chat.id, "Please use the buttons to continue.")
        elif language[message.chat.id] == "russian":
            ms = bot.send_message(message.chat.id, "Пожалуйста, используйте кнопки для продолжения.")
        add_message_id(message.chat.id, message.message_id)
        add_message_id(message.chat.id, ms.message_id)
        partial_tour(message)
        return
    # Получаем точки и отправляем информацию по каждой точке отдельным сообщением
    #nmess = bot.send_message(message.chat.id, f"{all_excursions[message.chat.id].get('name')}")
    #add_message_id(message.chat.id, nmess.message_id)

    details = points[mess]
    description = details.get('description', lang_vars['descrout'])
    photo_url = details.get('photo')
    audio_url = details.get('audio')
    # Отправляем фото, если оно есть и доступно
    if photo_url:
        if photo_url == "No file":
            nmess = bot.send_message(message.chat.id, text=f"{description}")
        else:
            try:
                response = requests.get(photo_url)
                if response.status_code == 200:
                    nmess = bot.send_photo(message.chat.id, photo_url, caption=f"{description}")
                else:
                    nmess = bot.send_message(message.chat.id, lang_vars['photoMis'])
            except requests.exceptions.RequestException:
                nmess = bot.send_message(message.chat.id, lang_vars['photoErr'])
        add_message_id(message.chat.id, nmess.message_id)
    # Отправляем аудио, если оно есть и доступно
    if audio_url:
        if audio_url != "No file":
            try:
                response = requests.get(audio_url)
                if response.status_code == 200:
                    nmess = bot.send_audio(message.chat.id, audio_url)
                else:
                    nmess = bot.send_message(message.chat.id, lang_vars['audioMis'])
            except requests.exceptions.RequestException:
                nmess = bot.send_message(message.chat.id, lang_vars['audioErr'])
            add_message_id(message.chat.id, nmess.message_id)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    points_new = all_excursions[message.chat.id].get('points', {})
    points_new = dict(
    sorted(
        points_new.items(),
        key=lambda item: item[1]['order']
        )
    )
    point_keys = list(points_new.keys())
    k = 0
    i = 0
    for shnm in point_keys:
        i += 1
        if shnm == mess:
            k = i
    cur_ex_ind[message.chat.id] = k
    if k < len(point_keys):
        button_next = types.KeyboardButton(lang_vars['button_text_next'])
        text = lang_vars['text']
        markup.add(button_next)
    else:
        text = lang_vars['text_end']

    for short_name in points_new:
        order = str(points[short_name].get('order'))
        button = types.KeyboardButton(f"{order}. {short_name}")
        markup.add(button)

    button1 = types.KeyboardButton(lang_vars['button_text_back'])
    markup.add(button1)
    nmess = bot.send_message(message.chat.id, text = text, reply_markup=markup)
    add_message_id(message.chat.id, nmess.message_id)

# Функция для обработки окна админа
def main_admin(message):
    global code_entering
    code_entering[message.chat.id] = 0
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if language[message.chat.id] == "spanish":
        button2 = types.KeyboardButton("Volver al menú")
        button1 = types.KeyboardButton("Gestión de excursiones")
        text1 = "Has entrado en la ventana de administración."
    elif language[message.chat.id] == "english":
        button2 = types.KeyboardButton("Go back to menu")
        button1 = types.KeyboardButton("Excursion management")
        text1 = "You have entered the admin window."
    elif language[message.chat.id] == "russian":
        button2 = types.KeyboardButton("Вернуться в меню")
        button1 = types.KeyboardButton("Управление экскурсиями")
        text1 = "Вы вошли в админское окно."
    
    markup.add(button1, button2)
    bot.send_message(message.chat.id, text=text1, reply_markup=markup)

###############################################################
#---------------------EDITION GLOBAL--------------------------#
###############################################################

modif_code = {}
full_data_mod = {}
curr_lang_glob = {}
admin_data = {}

@bot.message_handler(func=lambda message: user_state[message.chat.id] == 'BLOCK_EDIT')
def handle_block_action(message):
    global user_state, modif_code, full_data_mod, block_name, user_data, curr_lang_glob, admin_data
    full_data_mod[message.chat.id] = {}
    languages = ['Russian', 'English', 'Spanish']
    code = None
    curr_lang_glob[message.chat.id] = ""
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = START
        view_blocks(message)
        return
    elif message.text in ["Add tour language", "Agregar idioma del recorrido", "Добавить язык тура"]:
        blocks = database.child('blocks').get()
        for block_code, block_data in blocks.items():
            for lang in languages:
                if lang in block_data and block_data[lang].get('name') == block_name[message.chat.id]:
                    code = block_code
                    break
        full_data_mod[message.chat.id] = database.child('blocks').child(code).get()
        modif_code[message.chat.id] = code
        block_name[message.chat.id] = ""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for lang in languages:
            if lang not in full_data_mod[message.chat.id]:
                button = types.KeyboardButton(lang)
                markup.add(button)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Atrás")
            text = "Selecciona el idioma en el que agregarás el tour. A continuación se presentan únicamente aquellos idiomas que aún no están incluidos en el complejo de esta excursión. Si no hay botones con idiomas en el panel, entonces ya se han agregado todos los idiomas disponibles para esta excursión."
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Back")
            text = "Select the language in which you will add the excursion. Below are only those languages ​​that are not yet included in the complex of this excursion. If there are no buttons with languages ​​on the panel, then all available languages ​​have already been added for this excursion."
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Назад")
            text = "Выберите язык, на котором вы будете добавлять экскурсию. Ниже представлены лишь те языки, которых ещё нет в комплексе данной экскурсии. Если на панели кнопок с языками нет, значит для данной экскурсии добавлены уже все доступные языки."
        markup.add(button1)
        bot.send_message(message.chat.id, text = text, reply_markup=markup)
        user_state[message.chat.id] = 'ADD_LANDG_FIRST'

        user_data = getattr(bot, 'user_data', {})
        user_data[message.chat.id] = {'block_code': modif_code[message.chat.id], 'languages': full_data_mod[message.chat.id]}

        bot.user_data = user_data

    elif message.text in ["Seleccione el idioma del recorrido para editar", "Select the tour language for editing", "Выбрать язык тура для правки"]:
        blocks = database.child('blocks').get()
        for block_code, block_data in blocks.items():
            for lang in languages:
                if lang in block_data and block_data[lang].get('name') == block_name[message.chat.id]:
                    code = block_code
                    break
        full_data_mod[message.chat.id] = database.child('blocks').child(code).get()
        modif_code[message.chat.id] = code
        block_name[message.chat.id] = ""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for lang in languages:
            if lang in full_data_mod[message.chat.id]:
                button = types.KeyboardButton(lang)
                markup.add(button)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Atrás")
            text = "Seleccione el idioma de su recorrido. Este recorrido ya se ha agregado en todos los idiomas que se enumeran a continuación. Al seleccionar un idioma, podrás editar esta excursión agregada en ese idioma."
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Back")
            text = "Select the language of the tour. This tour has already been added in all the languages ​​listed below. By selecting a language, you will be able to edit this tour added in this language."
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Назад")
            text = "Выберите язык экскурсии. На всех указанных ниже языках данная экскурсия уже добавлена. Выбрав язык, вы сможете править данную экскурсию, добавленную на этом языке."
        markup.add(button1)
        bot.send_message(message.chat.id, text = text, reply_markup=markup)
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'

        #user_data = getattr(bot, 'user_data', {})
        admin_data[message.chat.id] = {'block_code': modif_code[message.chat.id], 'languages': full_data_mod[message.chat.id]}

        #bot.user_data = user_data

#-----------------------ADD LANGUAGE---------------------------

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ADD_LANDG_FIRST')
def handle_language_choice_add(message):
    global modif_code, user_data, user_state
    user_id = message.chat.id
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = START
        view_blocks(message)
        return
    lang_map = {"Ruso": "Russian", "Inglés": "English", "Español": "Spanish", "Russian": "Russian",
                "English": "English", "Spanish": "Spanish", "Русский": "Russian", "Английский": "English", "Испанский": "Spanish"}
    if message.text in lang_map:
        selected_lang = lang_map[message.text]
        if user_id not in user_data:
            user_data[user_id] = {'block_code': '', 'languages': {}}
        user_data[user_id]['current_language'] = selected_lang
        if 'languages' not in user_data[user_id]:
            user_data[user_id]['languages'] = {}
        if selected_lang not in user_data[user_id]['languages']:
            user_data[user_id]['languages'][selected_lang] = {'name': '', 'points': {}}
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Introduce el nombre de la excursión: ")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Enter the name of the excursion: ")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Введите название экскурсии: ")
        user_state[user_id] = 'ADD_BLOCK_NAME_FIRST'
    else:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Seleccione un idioma de las opciones proporcionadas.")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Please select a language from the options provided.")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Пожалуйста, выберите язык из предложенных вариантов.")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ADD_BLOCK_NAME_FIRST')
def add_block_name_add(message):
    global user_data, user_state
    user_id = message.chat.id
    user_data[user_id]['languages'][user_data[user_id]['current_language']]['name'] = message.text
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, text="Por favor introduzca una descripción de la excursión. Se mostrará al cliente en el menú de excursiones.")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, text="Please enter a description of the excursion. It will be displayed to the client in the excursion menu.")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, text="Введите, пожалуйста, описание экскурсии. Оно будет демонстрироваться клиенту в меню экскурсии.")
    user_state[user_id] = 'ADD_DESCRIPTION_MAIN_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ADD_DESCRIPTION_MAIN_FIRST')
def add_description_main_add(message):
    global user_data, user_state
    user_id = message.chat.id
    user_data[user_id]['languages'][user_data[user_id]['current_language']]['description'] = message.text
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        button1 = types.KeyboardButton("Si")
        button2 = types.KeyboardButton("No")
        markup.row(button1, button2)
        bot.send_message(user_id, text="¿Prefieres el audio?", reply_markup=markup)
    elif language[message.chat.id] == "english":
        button1 = types.KeyboardButton("Yes")
        button2 = types.KeyboardButton("No")
        markup.row(button1, button2)
        bot.send_message(user_id, text="Do we add audio tape?", reply_markup=markup)
    elif language[message.chat.id] == "russian":
        button1 = types.KeyboardButton("Да")
        button2 = types.KeyboardButton("Нет")
        markup.row(button1, button2)
        bot.send_message(user_id, text="Прикрепляем аудиофайл?", reply_markup=markup)
    user_state[user_id] = 'CONF_AUDIO_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'CONF_AUDIO_FIRST')
def check_audio_addition_add(message):
    global user_data, user_state
    user_id = message.chat.id
    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar un archivo de audio: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send an audio file: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Отправьте аудиофайл: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = 'ADD_AUDIO_FIRST'
    elif message.text in ["Нет", "No"]:
        user_data[user_id]['current_audio_url'] = "No file"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres foto?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add photo?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем фото?", reply_markup=markup)
        user_state[user_id] = 'CONF_PHOTO_FIRST'

@bot.message_handler(content_types=['audio'], func=lambda message: user_state.get(message.chat.id) == 'ADD_AUDIO_FIRST')
def add_audio_add(message):
    global user_data, user_state
    user_id = message.chat.id
    if user_id not in user_data:
        user_data[user_id] = {}
    try:
        file_info = bot.get_file(message.audio.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        if 'block_code' not in user_data[user_id] or 'current_language' not in user_data[user_id]:
            raise ValueError("Missing block_code or current_language")
        file_name = f"{user_data[user_id]['block_code']}_{user_data[user_id]['current_language']}_{len(user_data[user_id]['languages'][user_data[user_id]['current_language']]['points'])}.mp3"
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='audio/mpeg')
        blob.make_public()
        # Получение URL файла
        audio_url = blob.public_url
        user_data[user_id]['current_audio_url'] = audio_url
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres foto?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add photo?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем фото?", reply_markup=markup)
        user_state[user_id] = 'CONF_PHOTO_FIRST'
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de audio: {str(e)}")
        logger.error(f"Error processing audio file: {str(e)}")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'CONF_PHOTO_FIRST')
def check_photo_addition_add(message):
    global user_data, user_state
    user_id = message.chat.id
    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar una foto: ")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send photo: ")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Отправьте фотографию: ")
        user_state[user_id] = 'ADD_PHOTO_FIRST'
    elif message.text in ["Нет", "No"]:
        user_data[user_id]['current_photo_url'] = "No file"
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Agregue un nombre corto para el block de tour. Este es el nombre que el cliente verá en el botón: ")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Add a short name for this excursion block. This name will be seen by the client on the button: ")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Добавьте короткое имя для данного блока экскурсии. Это имя будет видеть клиент на кнопке: ")
        user_state[user_id] = 'SHORT_NAME_FIRST'

@bot.message_handler(content_types=['photo'], func=lambda message: user_state.get(message.chat.id) == 'ADD_PHOTO_FIRST')
def add_photo_add(message):
    global user_data, user_state
    user_id = message.chat.id
    if user_id not in user_data:
        user_data[user_id] = {}
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        if 'block_code' not in user_data[user_id] or 'current_language' not in user_data[user_id]:
            raise ValueError("Missing block_code or current_language")
        file_name = f"{user_data[user_id]['block_code']}_{user_data[user_id]['current_language']}_{len(user_data[user_id]['languages'][user_data[user_id]['current_language']]['points'])}_photo.jpg"
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='image/jpeg')
        blob.make_public()
        # Получение URL файла
        photo_url = blob.public_url
        user_data[user_id]['current_photo_url'] = photo_url
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Foto recibida. Agregue un nombre corto para el block de tour. Este es el nombre que el cliente verá en el botón: ")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Photo received. Add a short name for this excursion block. This name will be seen by the client on the button: ")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Фотография получена. Добавьте короткое имя для данного блока экскурсии. Это имя будет видеть клиент на кнопке: ")
        user_state[user_id] = 'SHORT_NAME_FIRST'
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de photo: {str(e)}")
        logger.error(f"Error processing photo file: {str(e)}")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'SHORT_NAME_FIRST')
def add_short_name_add(message):
    global user_data, user_state
    user_id = message.chat.id
    short_name = message.text
    user_data[user_id]['current_short_name'] = short_name
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, "Nombre corto recibido. Ahora agregue el número de secuencia:")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, "Short name received. Now add the serial number:")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, "Короткое имя получено. Теперь добавьте порядковый номер: ")
    user_state[user_id] = 'ADD_ORDER_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ADD_ORDER_FIRST')
def add_order_add(message):
    global user_data, user_state
    user_id = message.chat.id
    order = message.text
    user_data[user_id]['order'] = int(order)
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, "Nombre corto recibido. Ahora agrega una descripción")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, "Short name received. Now add a description")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, "Короткое имя получено. Теперь добавьте описание: ")
    user_state[user_id] = 'ADD_DESCRIPTION_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ADD_DESCRIPTION_FIRST')
def add_description_add(message):
    global user_data, user_state
    user_id = message.chat.id
    description = message.text
    current_lang = user_data[user_id]['current_language']
    short_name = user_data[user_id]['current_short_name']
    order = user_data[user_id]['order']
    user_data[user_id]['languages'][current_lang]['points'][short_name] = {
        'audio': user_data[user_id]['current_audio_url'],
        'photo': user_data[user_id]['current_photo_url'],
        'description': description,
        'order' : order
    }
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        markup.row('Agregar block', "Agregar idioma del recorrido", 'Terminar de agregar')
        bot.send_message(user_id, "Este parte añadido. ¿Qué sigue?", reply_markup=markup)
    elif language[message.chat.id] == "english":
        markup.row('Add block', "Add tour language", 'Finish adding')
        bot.send_message(user_id, "Block added. What's next?", reply_markup=markup)
    elif language[message.chat.id] == "russian":
        markup.row('Добавить блок', "Добавить язык тура", 'Завершить добавление')
        bot.send_message(user_id, "Блок добавлен. Что дальше?", reply_markup=markup)
    user_state[user_id] = 'CONFIRM_AUDIO_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'CONFIRM_AUDIO_FIRST')
def confirm_audio_add(message):
    global user_state, user_data
    user_id = message.chat.id
    if message.text in ['Добавить блок', 'Add block', 'Agregar block']:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres el audio?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add audio tape?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем аудиофайл?", reply_markup=markup)
        user_state[user_id] = 'CONF_AUDIO_FIRST'
    elif message.text in ["Добавить язык тура", "Add tour language", "Agregar idioma del recorrido"]:
        user_state[message.chat.id] == 'BLOCK_EDIT'
        handle_block_action(message)
    elif message.text in ['Завершить добавление', 'Finish adding', 'Terminar de agregar']:
        user_data = getattr(bot, 'user_data', {}).get(message.chat.id, {})
        block_code = user_data['block_code']
        languages = user_data['languages']
   
    # Сохранение данных в Firebase Realtime Database
        block_ref = database.child('blocks').child(block_code)
        block_ref.set(languages)
        bot.user_data = getattr(bot, 'user_data', {})
        bot.user_data[message.chat.id] = {}
        user_state[message.chat.id] = START
        view_blocks(message)

#-----------------------FIN ADD LANGUAGE---------------------------

#-----------------------EDIT LANGUAGE------------------------------
ord_global = {}
@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'EDIT_LANG_FIRST')
def edit_lang_start(message):
    global curr_lang_glob, user_state
    lang_map = {"Ruso": "Russian", "Inglés": "English", "Español": "Spanish", "Russian": "Russian",
                "English": "English", "Spanish": "Spanish", "Русский": "Russian", "Английский": "English", "Испанский": "Spanish"}
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = START
        view_blocks(message)
        return
    if message.text in lang_map:
        curr_lang_glob[message.chat.id] = message.text
        selected_lang = lang_map[curr_lang_glob[message.chat.id]]
        curr_lang_glob[message.chat.id] = selected_lang
        handle_edit_lang(message)
    else:
        if language[message.chat.id] == "spanish":
            bot.send_message(message.chat.id, text="Seleccione un idioma de las opciones proporcionadas.")
        elif language[message.chat.id] == "english":
            bot.send_message(message.chat.id, text="Please select a language from the options provided.")
        elif language[message.chat.id] == "russian":
            bot.send_message(message.chat.id, text="Пожалуйста, выберите язык из предложенных вариантов.")
        user_state[message.chat.id] = START
        view_blocks(message)

def handle_edit_lang(message):
    global user_state, full_data_mod, button_lst
    user_id = message.chat.id
    button_lst[message.chat.id] = []
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    full_data_mod[message.chat.id] = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).get()
    if language[message.chat.id] == "spanish":
        button1 = types.KeyboardButton("Cambiar nombre del recorrido")
        button2 = types.KeyboardButton("Cambiar descripción de la excursión")
        button3 = types.KeyboardButton("Eliminar excursión en este idioma")
        button4 = types.KeyboardButton("Añadir bloque de excursiones")
        button5 = types.KeyboardButton("Atrás")
        btn = "Cambiar: "
        text="Seleccione la acción que desea realizar:"
    elif language[message.chat.id] == "english":
        button1 = types.KeyboardButton("Change excursion name")
        button2 = types.KeyboardButton("Change excursion description")
        button3 = types.KeyboardButton("Delete tour in this language")
        button4 = types.KeyboardButton("Add excursion block")
        button5 = types.KeyboardButton("Back")
        btn = "Modify: "
        text="Select the action you want to perform:"
    elif language[message.chat.id] == "russian":
        button1 = types.KeyboardButton("Изменить название экскурсии")
        button2 = types.KeyboardButton("Изменить описание экскурсии")
        button3 = types.KeyboardButton("Удалить экскурсию на данном языке")
        button4 = types.KeyboardButton("Добавить блок экскурсии")
        button5 = types.KeyboardButton("Назад")
        btn = "Изменить: "
        text="Выберите действие, которое вы хотите совершить:"
    markup.row(button1)
    markup.row(button2)
    markup.row(button3)
    markup.row(button4)
    points = full_data_mod[message.chat.id].get('points', {})
    points = dict(
    sorted(
            points.items(),
            key=lambda item: item[1]['order']
          )
    )
    for short_name in points:
        order = str(points[short_name].get('order'))
        button = types.KeyboardButton(f"{btn}{order}. {short_name}")
        markup.add(button)
        button_lst[message.chat.id].append(f"{btn}{order}. {short_name}")
    markup.row(button5)
    bot.send_message(user_id, text=text, reply_markup=markup)
    user_state[user_id] = 'EDIT_LANG_HANGLE_SECOND'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'EDIT_LANG_HANGLE_SECOND')
def handle_edit_lang_selection(message):
    global modif_code, user_data, user_state, full_data_mod, button_lst
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = START
        view_blocks(message)
        return
    
    elif message.text in ["Изменить название экскурсии", "Change excursion name", "Cambiar nombre del recorrido"]:
        name = full_data_mod[message.chat.id]['name']
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            text = f"Nombre de la excursión actual: {name}\nIntroduzca un nuevo nombre:"
            button = types.KeyboardButton("Atrás")
        elif language[message.chat.id] == "english":
            text = f"Current tour name: {name}\nEnter a new name:"
            button = types.KeyboardButton("Back")
        elif language[message.chat.id] == "russian":
            text = f"Текущее название экскурсии: {name}\nВведите новое название:"
            button = types.KeyboardButton("Назад")
        markup.row(button)
        bot.send_message(message.chat.id, text=text, reply_markup=markup)
        user_state[message.chat.id] = 'EDIT_LANG_NAME_THIRD'

    elif message.text in ["Изменить описание экскурсии", "Change excursion description", "Change excursion description"]:
        description = full_data_mod[message.chat.id]['description']
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            text = f"Descripción de la excursión actual: {description}\nIntroduzca un nuevo descripción:"
            button = types.KeyboardButton("Atrás")
        elif language[message.chat.id] == "english":
            text = f"Current tour description: {description}\nEnter a new description:"
            button = types.KeyboardButton("Back")
        elif language[message.chat.id] == "russian":
            text = f"Текущее описание экскурсии: {description}\nВведите новое описание:"
            button = types.KeyboardButton("Назад")
        markup.row(button)
        bot.send_message(message.chat.id, text=text, reply_markup=markup)
        user_state[message.chat.id] = 'EDIT_LANG_DESCRIPTION_THIRD'

    elif message.text in ["Удалить экскурсию на данном языке", "Delete tour in this language", "Eliminar excursión en este idioma"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Sí")
            button2 = types.KeyboardButton("Atrás")
            text = "¿Estás seguro de que deseas eliminar el recorrido en este idioma?"
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("Back")
            text = "Are you sure you want to delete the tour in this language?"
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Назад")
            text = "Вы действительно хотите удалить экскурсию на данном языке?"
        markup.row(button1)
        markup.row(button2)
        bot.send_message(message.chat.id, text=text, reply_markup=markup)
        user_state[message.chat.id] = 'EDIT_LANG_BLOCK_DEL_THIRD'

    elif message.text in ["Добавить блок экскурсии", "Add excursion block", "Añadir bloque de excursiones"]:
        admin_data[message.chat.id] = {'block_code': modif_code[message.chat.id], 'languages': database.child('blocks').child(modif_code[message.chat.id]).get()}
        edit_start_add_block(message)

    elif message.text in button_lst[message.chat.id]:
        edit_selected_block(message)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'EDIT_LANG_NAME_THIRD')
def edit_lang_rename(message):
    global user_state
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        handle_edit_lang(message)
        return

    database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('name').set(message.text)
    if language[message.chat.id] == "spanish":
        text = f"El nombre de la excursión se cambió correctamente a {message.text}"
    elif language[message.chat.id] == "english":
        text = f"Tour name successfully changed to {message.text}"
    elif language[message.chat.id] == "russian":
        text = f"Название экскурсии успешно изменено на {message.text}"
    bot.send_message(message.chat.id, text=text)
    user_state[message.chat.id] = 'EDIT_LANG_FIRST'
    handle_edit_lang(message)
    return

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'EDIT_LANG_DESCRIPTION_THIRD')
def edit_description_rename(message):
    global user_state
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        handle_edit_lang(message)
        return

    database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('description').set(message.text)
    if language[message.chat.id] == "spanish":
        text = f"La descripción de la excursión se cambió correctamente a {message.text}"
    elif language[message.chat.id] == "english":
        text = f"Tour description successfully changed to {message.text}"
    elif language[message.chat.id] == "russian":
        text = f"Описание экскурсии успешно изменено на {message.text}"
    bot.send_message(message.chat.id, text=text)
    user_state[message.chat.id] = 'EDIT_LANG_FIRST'
    handle_edit_lang(message)
    return

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'EDIT_LANG_BLOCK_DEL_THIRD')
def edit_lang_block_del(message):
    global user_state
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        handle_edit_lang(message)
        return
    elif message.text in ['Да', 'Yes', 'Sí']:
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).delete()
        if language[message.chat.id] == "spanish":
            text = f"Excursión en {curr_lang_glob[message.chat.id]} eliminada correctamente"
        elif language[message.chat.id] == "english":
            text = f"Tour in language {curr_lang_glob[message.chat.id]} successfully deleted"
        elif language[message.chat.id] == "russian":
            text = f"Экскурсия на языке {curr_lang_glob[message.chat.id]} успешно удалена"
        user_state[message.chat.id] = START
        view_blocks(message)

def edit_start_add_block(message):
    global admin_data, user_state
    user_id = message.chat.id
    admin_data[user_id]['current_language'] = curr_lang_glob[message.chat.id]
    admin_data[user_id]['languages'][admin_data[user_id]['current_language']]['name'] = full_data_mod[message.chat.id]['name']
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        button1 = types.KeyboardButton("Si")
        button2 = types.KeyboardButton("No")
        markup.row(button1, button2)
        bot.send_message(user_id, text="¿Prefieres el audio?", reply_markup=markup)
    elif language[message.chat.id] == "english":
        button1 = types.KeyboardButton("Yes")
        button2 = types.KeyboardButton("No")
        markup.row(button1, button2)
        bot.send_message(user_id, text="Do we add audio tape?", reply_markup=markup)
    elif language[message.chat.id] == "russian":
        button1 = types.KeyboardButton("Да")
        button2 = types.KeyboardButton("Нет")
        markup.row(button1, button2)
        bot.send_message(user_id, text="Прикрепляем аудиофайл?", reply_markup=markup)
    user_state[user_id] = 'ED_CONF_AUDIO_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ED_CONF_AUDIO_FIRST')
def check_audio_addition_edit(message):
    global admin_data, user_state
    user_id = message.chat.id
    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar un archivo de audio: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send an audio file: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Отправьте аудиофайл: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = 'ED_ADD_AUDIO_FIRST'
    elif message.text in ["Нет", "No"]:
        admin_data[user_id]['current_audio_url'] = "No file"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres foto?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add photo?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем фото?", reply_markup=markup)
        user_state[user_id] = 'ED_CONF_PHOTO_FIRST'

@bot.message_handler(content_types=['audio'], func=lambda message: user_state.get(message.chat.id) == 'ED_ADD_AUDIO_FIRST')
def add_audio_edit(message):
    global admin_data, user_state
    user_id = message.chat.id
    if user_id not in admin_data:
        admin_data[user_id] = {}
    try:
        file_info = bot.get_file(message.audio.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        if 'block_code' not in admin_data[user_id] or 'current_language' not in admin_data[user_id]:
            raise ValueError("Missing block_code or current_language")
        file_name = f"{admin_data[user_id]['block_code']}_{admin_data[user_id]['current_language']}_{len(admin_data[user_id]['languages'][admin_data[user_id]['current_language']]['points'])}.mp3"
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='audio/mpeg')
        blob.make_public()
        # Получение URL файла
        audio_url = blob.public_url
        admin_data[user_id]['current_audio_url'] = audio_url
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="¿Prefieres foto?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Do we add photo?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(user_id, text="Прикрепляем фото?", reply_markup=markup)
        user_state[user_id] = 'ED_CONF_PHOTO_FIRST'
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de audio: {str(e)}")
        logger.error(f"Error processing audio file: {str(e)}")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ED_CONF_PHOTO_FIRST')
def check_photo_addition_edit(message):
    global admin_data, user_state
    user_id = message.chat.id
    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar una foto: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send photo: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Отправьте фотографию: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = 'ED_ADD_PHOTO_FIRST'
    elif message.text in ["Нет", "No"]:
        admin_data[user_id]['current_photo_url'] = "No file"
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Agregue un nombre corto para el block de tour. Este es el nombre que el cliente verá en el botón: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Add a short name for this excursion block. This name will be seen by the client on the button: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Добавьте короткое имя для данного блока экскурсии. Это имя будет видеть клиент на кнопке: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = 'ED_SHORT_NAME_FIRST'

@bot.message_handler(content_types=['photo'], func=lambda message: user_state.get(message.chat.id) == 'ED_ADD_PHOTO_FIRST')
def add_photo_edit(message):
    global admin_data, user_state
    user_id = message.chat.id
    if user_id not in admin_data:
        admin_data[user_id] = {}
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        if 'block_code' not in admin_data[user_id] or 'current_language' not in admin_data[user_id]:
            raise ValueError("Missing block_code or current_language")
        file_name = f"{admin_data[user_id]['block_code']}_{admin_data[user_id]['current_language']}_{len(admin_data[user_id]['languages'][admin_data[user_id]['current_language']]['points'])}_photo.jpg"
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='image/jpeg')
        blob.make_public()
        # Получение URL файла
        photo_url = blob.public_url
        admin_data[user_id]['current_photo_url'] = photo_url
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Foto recibida. Agregue un nombre corto para el block de tour. Este es el nombre que el cliente verá en el botón: ")
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Photo received. Add a short name for this excursion block. This name will be seen by the client on the button: ")
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Фотография получена. Добавьте короткое имя для данного блока экскурсии. Это имя будет видеть клиент на кнопке: ")
        user_state[user_id] = 'ED_SHORT_NAME_FIRST'
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de photo: {str(e)}")
        logger.error(f"Error processing photo file: {str(e)}")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ED_SHORT_NAME_FIRST')
def add_short_name_edit(message):
    global admin_data, user_state
    user_id = message.chat.id
    short_name = message.text
    admin_data[user_id]['current_short_name'] = short_name
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, "Nombre corto recibido. Ahora agregue el número de secuencia:")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, "Short name received. Now add the serial number:")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, "Короткое имя получено. Теперь добавьте порядковый номер: ")
    user_state[user_id] = 'ED_ADD_ORDER_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ED_ADD_ORDER_FIRST')
def add_order_edit(message):
    global admin_data, user_state
    user_id = message.chat.id
    order = message.text
    admin_data[user_id]['order'] = int(order)
    if language[message.chat.id] == "spanish":
        bot.send_message(user_id, "Ahora agrega una descripción")
    elif language[message.chat.id] == "english":
        bot.send_message(user_id, "Now add a description")
    elif language[message.chat.id] == "russian":
        bot.send_message(user_id, "Теперь добавьте описание: ")
    user_state[user_id] = 'ED_ADD_DESCRIPTION_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ED_ADD_DESCRIPTION_FIRST')
def add_description_edit(message):
    global admin_data, user_state, ord_global
    user_id = message.chat.id
    ord_global[user_id] = 1000
    description = message.text
    current_lang = admin_data[user_id]['current_language']
    short_name = admin_data[user_id]['current_short_name']
    order = admin_data[user_id]['order']
    ord_global[user_id] = order
    admin_data[user_id]['languages'][current_lang]['points'][short_name] = {
        'audio': admin_data[user_id]['current_audio_url'],
        'photo': admin_data[user_id]['current_photo_url'],
        'description': description,
        'order' : order
    }

    for srt_nm in admin_data[user_id]['languages'][current_lang]['points']:
        cur_ord = admin_data[user_id]['languages'][current_lang]['points'][srt_nm]['order']
        if srt_nm != short_name and cur_ord >= ord_global[user_id]:
            admin_data[user_id]['languages'][current_lang]['points'][srt_nm]['order'] = cur_ord + 1

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        markup.row('Terminar de agregar', 'Cancelar')
        bot.send_message(user_id, "Este parte añadido", reply_markup=markup)
    elif language[message.chat.id] == "english":
        markup.row('Finish adding', 'Cancel')
        bot.send_message(user_id, "Block added", reply_markup=markup)
    elif language[message.chat.id] == "russian":
        markup.row('Завершить добавление', 'Отмена')
        bot.send_message(user_id, "Блок добавлен", reply_markup=markup)
    user_state[user_id] = 'ED_CONFIRM_AUDIO_FIRST'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'ED_CONFIRM_AUDIO_FIRST')
def confirm_audio_edit(message):
    global user_state, admin_data
    user_id = message.chat.id
    ord_global[user_id] = 1000
    if message.text in ['Завершить добавление', 'Finish adding', 'Terminar de agregar']:
        current_lang = admin_data[user_id]['current_language']
        points = admin_data[user_id]['languages'][current_lang]['points']
    # Сохранение данных в Firebase Realtime Database
        #print(points, "\n\n")
        #print(database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').get(), "\n\n")
        block_ref = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points')
        block_ref.delete()
        block_ref.set(points)
        admin_data[message.chat.id] = {'block_code': modif_code[message.chat.id], 'languages': {}}
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        handle_edit_lang(message)
    else:
        admin_data[message.chat.id] = {'block_code': modif_code[message.chat.id], 'languages': {}}
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        handle_edit_lang(message)
        
short_name = {}
def edit_selected_block(message):
    global full_data_mod, user_state, short_name
    lang_vars = get_language_variables(message.chat.id)
    pattern = r"\d+\.\s(.+)$"
    match = re.search(pattern, message.text)
    if match:
        short_name[message.chat.id] = match.group(1)
    edit_selected_block_cont(message)

def edit_selected_block_cont(message):
    global full_data_mod, user_state, short_name
    lang_vars = get_language_variables(message.chat.id)
    full_data_mod[message.chat.id] = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).get()
    points = full_data_mod[message.chat.id]['points']
    details = points[short_name[message.chat.id]]
    description = details.get('description', lang_vars['descrout'])
    photo_url = details.get('photo')
    audio_url = details.get('audio')
    order = details.get('order')
    bot.send_message(message.chat.id, text=f"{order}. {short_name[message.chat.id]}")
    # Отправляем фото, если оно есть и доступно
    if photo_url:
        if photo_url == "No file":
            nmess = bot.send_message(message.chat.id, text=f"{lang_vars['descr']}: {description}")
        else:
            try:
                response = requests.get(photo_url)
                if response.status_code == 200:
                    nmess = bot.send_photo(message.chat.id, photo_url, caption=f"{lang_vars['descr']}: {description}")
                else:
                    nmess = bot.send_message(message.chat.id, lang_vars['photoMis'])
            except requests.exceptions.RequestException:
                nmess = bot.send_message(message.chat.id, lang_vars['photoErr'])
        add_message_id(message.chat.id, nmess.message_id)
    # Отправляем аудио, если оно есть и доступно
    if audio_url:
        if audio_url != "No file":
            try:
                response = requests.get(audio_url)
                if response.status_code == 200:
                    nmess = bot.send_audio(message.chat.id, audio_url)
                else:
                    nmess = bot.send_message(message.chat.id, lang_vars['audioMis'])
            except requests.exceptions.RequestException:
                nmess = bot.send_message(message.chat.id, lang_vars['audioErr'])
            add_message_id(message.chat.id, nmess.message_id)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if language[message.chat.id] == "spanish":
        button1 = types.KeyboardButton("Eliminar bloque")
        button2 = types.KeyboardButton("Editar nombre corto")
        button3 = types.KeyboardButton("Editar audio")
        button4 = types.KeyboardButton("Editar foto")
        button5 = types.KeyboardButton("Editar descripción")
        button = types.KeyboardButton("Atrás")
        text = "Selecciona la acción que deseas realizar en el bloque."
    elif language[message.chat.id] == "english":
        button1 = types.KeyboardButton("Remove block")
        button2 = types.KeyboardButton("Edit short name")
        button3 = types.KeyboardButton("Edit audio")
        button4 = types.KeyboardButton("Edit photo")
        button5 = types.KeyboardButton("Edit description")
        button = types.KeyboardButton("Back")
        text = "Select the action you want to perform on the block."
    elif language[message.chat.id] == "russian":
        button1 = types.KeyboardButton("Удалить блок")
        button2 = types.KeyboardButton("Изменить короткое имя")
        button3 = types.KeyboardButton("Изменить аудио")
        button4 = types.KeyboardButton("Изменить фото")
        button5 = types.KeyboardButton("Изменить описание")
        button = types.KeyboardButton("Назад")
        text = "Выберите действие, которое вы хотите совершить над блоком."
    markup.row(button2, button3)
    markup.row(button4, button5)
    markup.row(button1)
    markup.row(button)
    bot.send_message(message.chat.id, text=text, reply_markup=markup)
    user_state[message.chat.id] = 'EDIT_BLOCK_GOLD'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'EDIT_BLOCK_GOLD')
def handle_block_edit_gold(message):
    global user_state
    if message.text in ['Назад', 'Back', 'Atrás']:
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        short_name[message.chat.id] = ""
        handle_edit_lang(message)
        return
    
    elif message.text in ["Удалить блок", "Remove block", "Eliminar bloque"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Sí")
            button2 = types.KeyboardButton("Atrás")
            text = "¿Estás seguro de que deseas eliminar el block?"
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("Back")
            text = "Are you sure you want to delete the block?"
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Назад")
            text = "Вы действительно хотите удалить блок?"
        markup.row(button1)
        markup.row(button2)
        bot.send_message(message.chat.id, text=text, reply_markup=markup)
        user_state[message.chat.id] = 'BLOCK_DELETE_GOLD'

    elif message.text in ["Изменить короткое имя", "Edit short name", "Editar nombre corto"]:
        if language[message.chat.id] == "spanish":
            text = "Ingrese un nuevo nombre corto para el bloque. Aparecerá en el botón del cliente y en el menú del editor."
        elif language[message.chat.id] == "english":
            text = "Enter a new short name for the block. It will appear on the client's button and in the editor menu."
        elif language[message.chat.id] == "russian":
            text = "Введите новое короткое имя блока. Оно появится на кнопке у клиента и в меню редактора."
        bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
        user_state[message.chat.id] = 'BLOCK_SHORT_NAME_GOLD'

    elif message.text in ["Изменить аудио", "Edit audio", "Editar audio"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(message.chat.id, text="¿Prefieres el audio?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(message.chat.id, text="Do we add audio tape?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(message.chat.id, text="Прикрепляем аудиофайл?", reply_markup=markup)
        user_state[message.chat.id] = 'CONF_AUDIO_GOLD'

    elif message.text in ["Изменить фото", "Edit photo", "Editar foto"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if language[message.chat.id] == "spanish":
            button1 = types.KeyboardButton("Si")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(message.chat.id, text="¿Prefieres el foto?", reply_markup=markup)
        elif language[message.chat.id] == "english":
            button1 = types.KeyboardButton("Yes")
            button2 = types.KeyboardButton("No")
            markup.row(button1, button2)
            bot.send_message(message.chat.id, text="Do we add photo?", reply_markup=markup)
        elif language[message.chat.id] == "russian":
            button1 = types.KeyboardButton("Да")
            button2 = types.KeyboardButton("Нет")
            markup.row(button1, button2)
            bot.send_message(message.chat.id, text="Прикрепляем фото?", reply_markup=markup)
        user_state[message.chat.id] = 'CONF_PHOTO_GOLD'

    elif message.text in ["Изменить описание", "Edit description", "Editar descripción"]:
        if language[message.chat.id] == "spanish":
            text = "Ingrese una nueva descripción de bloque."
        elif language[message.chat.id] == "english":
            text = "Enter a new block description."
        elif language[message.chat.id] == "russian":
            text = "Введите новое описание блока."
        bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
        user_state[message.chat.id] = 'BLOCK_DESCRIPTION_GOLD'

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'BLOCK_DELETE_GOLD')
def handle_block_delete_gold(message):
    global user_state, short_name
    if message.text in ['Назад', 'Back', 'Atrás']:
        short_name[message.chat.id] = ""
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        handle_edit_lang(message)
        return
    order = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).child('order').get()
    block_ref_name = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id])
    block_ref_name.delete()
    points = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').get()
    for srt_nm in points:
        cur_ord = points[srt_nm]['order']
        if cur_ord > order:
            points[srt_nm]['order'] = cur_ord - 1
    block_ref = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points')
    block_ref.set(points)
    if language[message.chat.id] == "spanish":
        text = "Bloque eliminado exitosamente."
    elif language[message.chat.id] == "english":
        text = "Block successfully removed."
    elif language[message.chat.id] == "russian":
        text = "Блок успешно удалён."
    bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
    short_name[message.chat.id] = ""
    user_state[message.chat.id] = 'EDIT_LANG_FIRST'
    handle_edit_lang(message)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'BLOCK_SHORT_NAME_GOLD')
def handle_block_short_name_gold(message):
    global user_state, short_name
    point = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).get()
    database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).delete()
    database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(message.text).set(point)

    if language[message.chat.id] == "spanish":
        text = f"El nombre del bloque se cambió correctamente a {message.text}."
    elif language[message.chat.id] == "english":
        text = f"Block successfully renamed to {message.text}."
    elif language[message.chat.id] == "russian":
        text = f"Блок успешно переименован на {message.text}."
    bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
    short_name[message.chat.id] = message.text
    user_state[message.chat.id] = 'EDIT_LANG_FIRST'
    edit_selected_block_cont(message)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'CONF_AUDIO_GOLD')
def handle_block_audio_gold(message):
    global user_state, short_name
    point = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).get()
    user_id = message.chat.id

    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar un archivo de audio: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send an audio file: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, text="Отправьте аудиофайл: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = 'ADD_AUDIO_GOLD'
    elif message.text in ["Нет", "No"]:
        point['audio'] = "No file"
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).child('audio').delete()
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).set(point)
        if language[message.chat.id] == "spanish":
            text = "Añadiendo completado."
        elif language[message.chat.id] == "english":
            text = "Addition completed."
        elif language[message.chat.id] == "russian":
            text = "Добавление завершено."
        bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())

        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        edit_selected_block_cont(message)

@bot.message_handler(content_types=['audio'], func=lambda message: user_state.get(message.chat.id) == 'ADD_AUDIO_GOLD')
def add_block_audio_gold(message):
    global user_state, short_name
    point = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).get()
    user_id = message.chat.id
    try:
        file_info = bot.get_file(message.audio.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = f"{modif_code[message.chat.id]}_{curr_lang_glob[message.chat.id]}_{short_name[message.chat.id]}.mp3"
        #print(file_name)
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='audio/mpeg')
        blob.make_public()
        # Получение URL файла
        audio_url = blob.public_url
        point['audio'] = audio_url
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).child('audio').delete()
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).set(point)
        if language[message.chat.id] == "spanish":
            text = "Añadiendo completado."
        elif language[message.chat.id] == "english":
            text = "Addition completed."
        elif language[message.chat.id] == "russian":
            text = "Добавление завершено."
        bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
        
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        edit_selected_block_cont(message)
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de audio: {str(e)}")
        logger.error(f"Error processing audio file: {str(e)}")
        edit_selected_block_cont(message)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'CONF_PHOTO_GOLD')
def handle_block_photo_gold(message):
    global user_state, short_name
    point = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).get()
    user_id = message.chat.id
    if message.text in ["Да", "Yes", "Si"]:
        if language[message.chat.id] == "spanish":
            bot.send_message(user_id, text="Enviar una foto: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "english":
            bot.send_message(user_id, text="Send photo: ", reply_markup=types.ReplyKeyboardRemove())
        elif language[message.chat.id] == "russian":
            bot.send_message(user_id, "Отправьте фотографию: ", reply_markup=types.ReplyKeyboardRemove())
        user_state[user_id] = 'ADD_PHOTO_GOLD'
    elif message.text in ["Нет", "No"]:
        point['photo'] = "No file"
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).child('photo').delete()
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).set(point)
        if language[message.chat.id] == "spanish":
            text = "Añadiendo completado."
        elif language[message.chat.id] == "english":
            text = "Addition completed."
        elif language[message.chat.id] == "russian":
            text = "Добавление завершено."
        bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
        
        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        edit_selected_block_cont(message)

@bot.message_handler(content_types=['photo'], func=lambda message: user_state.get(message.chat.id) == 'ADD_PHOTO_GOLD')
def add_photo_edit(message):
    global short_name, user_state
    point = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).get()
    user_id = message.chat.id
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = f"{modif_code[message.chat.id]}_{curr_lang_glob[message.chat.id]}_{short_name[message.chat.id]}_photo.jpg"
        # Загрузка файла в Firebase Storage
        blob = bucket.blob(file_name)
        blob.upload_from_string(downloaded_file, content_type='image/jpeg')
        blob.make_public()
        # Получение URL файла
        photo_url = blob.public_url
        point['photo'] = photo_url
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).child('photo').delete()
        database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).set(point)
        if language[message.chat.id] == "spanish":
            text = "Añadiendo completado."
        elif language[message.chat.id] == "english":
            text = "Addition completed."
        elif language[message.chat.id] == "russian":
            text = "Добавление завершено."
        bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())

        user_state[message.chat.id] = 'EDIT_LANG_FIRST'
        edit_selected_block_cont(message)
    except Exception as e:
        bot.send_message(user_id, f"Error al procesar el archivo de photo: {str(e)}")
        logger.error(f"Error processing photo file: {str(e)}")
        edit_selected_block_cont(message)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id) == 'BLOCK_DESCRIPTION_GOLD')
def handle_block_description_gold(message):
    global user_state, short_name
    point = database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).get()
    database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).child('description').delete()
    point['description'] = message.text
    database.child('blocks').child(modif_code[message.chat.id]).child(curr_lang_glob[message.chat.id]).child('points').child(short_name[message.chat.id]).set(point)

    if language[message.chat.id] == "spanish":
        text = "Descripción agregada"
    elif language[message.chat.id] == "english":
        text = "Description added"
    elif language[message.chat.id] == "russian":
        text = "Описание добавлено"
    bot.send_message(message.chat.id, text=text, reply_markup=types.ReplyKeyboardRemove())
    
    user_state[message.chat.id] = 'EDIT_LANG_FIRST'
    edit_selected_block_cont(message)

#-----------------------FIN EDIT LANGUAGE--------------------------

# Запуск бота
if __name__ == '__main__':
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error("Error while polling: %s", str(e))
