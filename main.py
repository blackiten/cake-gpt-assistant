import os
import pandas as pd
import json
from openai import OpenAI
from dotenv import load_dotenv
from langchain_community.chat_message_histories import ChatMessageHistory
from aiogram import Bot, Dispatcher, types
import asyncio

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY")

client = OpenAI(api_key=OPEN_AI_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

LL_MODEL = 'gpt-4o-mini'
ORDERS_FILE = 'orders_file.csv'
system_content = '''Ты помощник кондитера, общаешься с клиентами в чате и записываешь их заказы, чтобы передать кондитеру.
Твоя задача расспросить у клиента: имя, размер торта, какой повод и в какой день доставить. 
Общайся вежливо, можешь шутить. Не записывай в таблицу, пока клиент не ответил на все вопросы. Сначала уточни все данные.'''

HISTORY = {}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fillout_order_data",
            "description": "Get user's name, cake size, reason for celebration and date when cake should be baked and write all these data for order",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "user's name, e.g. Ivan Ivanov",
                    },
                    "cake_size": {
                        "type": "string",
                        "description": "cake size: small (20 cm), medium (30 cm) or big (45 cm)"
                    },
                    "celebration": {
                        "type": "string",
                        "description": "a reason to buy a cake, e.g. birthday",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "date when cake should be delivered",
                    },
                },
                "required": ["name", "cake_size", "celebration", "due_date"]
            }
        }
    }
]

def write_to_file(file_data, file_name):
    with open(file_name, 'w', encoding='utf-8') as file:
        file.write(file_data)

def append_to_file(new_line, file_name):
    with open(file_name, 'a', encoding='utf-8') as file:
        file.write('\n' + new_line)

def fillout_order_data(name, cake_size, celebration, due_date, orders_file=ORDERS_FILE):
    if os.path.exists(orders_file):
        pd.read_csv(orders_file, sep=';', quotechar='"')
    else:
        write_to_file('name;cake_size;celebration;due_date', orders_file)

    line_for_file = f'"{name}";"{cake_size}";"{celebration}";"{due_date}"'
    append_to_file(line_for_file, orders_file)

    return f"{name}, заказ успешно принят!"

def get_user_history(user_id):
    global HISTORY
    if user_id not in HISTORY:
        HISTORY[user_id] = ChatMessageHistory()
    return HISTORY[user_id]

def set_user_history(user_id, question, answer):
    history = get_user_history(user_id)
    history.add_user_message(question)
    history.add_ai_message(answer)

async def get_answer_gpt_func(user_id, user_content):
    history = get_user_history(user_id)
    chat_history = history.messages

    user_message = f"user_id: {user_id}\nChat History:\n{chat_history}\nClient: {user_content}"
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message}
    ]

    try:
        response = client.chat.completions.create(
            model=LL_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        print("API Response:", response)

        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            tool_call = tool_calls[0]
            function_name = tool_call.function.name
            function_arguments = json.loads(tool_call.function.arguments)

            print(f"Вызов функции: {function_name}, аргументы: {function_arguments}")

            if function_name == "fillout_order_data":
                tool_response = fillout_order_data(
                    name=function_arguments["name"],
                    cake_size=function_arguments["cake_size"],
                    celebration=function_arguments["celebration"],
                    due_date=function_arguments["due_date"]
                )
                return tool_response

    except Exception as e:
        return f"Ошибка взаимодействия с OpenAI: {e}"

    answer = response.choices[0].message.content
    set_user_history(user_id, user_content, answer)
    return answer

async def start_command(message: types.Message):
    await message.reply("Привет! Я помощник кондитера. Напишите, что вы хотите узнать или заказать!")

async def process_user_message(user_id: int, user_content: str) -> str:
    response = await get_answer_gpt_func(user_id, user_content)
    return response

async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_content = message.text

    response = await process_user_message(user_id, user_content)

    await message.reply(response)

async def main():
    dp.message.register(handle_message)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())