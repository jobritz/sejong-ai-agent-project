from ollama import chat

response = chat(
    model='llama3',
    messages=[
        {'role': 'user', 'content': 'Hallo'}
    ]
)

print(response['message']['content'])