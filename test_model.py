import requests
import json

def chat(prompt):
    response = requests.post(
        "http://localhost:8000/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        json={
            "model": "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.7
        }
    )
    
    result = response.json()
    print(result['choices'][0]['message']['content'])

# Test it
chat("Write a Python function to reverse a linked list")