import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# Configure the LLM
# This expects the OPENAI_API_KEY environment variable to be set
def get_llm():
    # Explicitly grab the key and pass it in
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in the environment variables.")
        
    # Strip quotes if they accidentally carried over from the .env file
    api_key = api_key.strip('"').strip("'")
    
    print(f"Debug: Loaded OpenAI API Key starting with: {api_key[:10]}...")
    
    return ChatOpenAI(
        model="gpt-4o-mini", # or gpt-3.5-turbo, gpt-4o
        temperature=0.7,
        api_key=api_key,
    )

def generate_chat_response(messages_history: list, new_user_message: str) -> str:
    """
    Generates a response from OpenAI based on the conversation history.
    messages_history is a list of dictionaries with 'role' ('user' or 'assistant') and 'content'.
    """
    llm = get_llm()
    
    langchain_messages = []
    # Add a system prompt if needed to guide the AI
    langchain_messages.append(SystemMessage(content="You are a helpful AI assistant for Ai Funda, an application dealing with financial and stock data. Be concise and informative."))
    
    for msg in messages_history:
        if msg['role'] == 'user':
            langchain_messages.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            langchain_messages.append(AIMessage(content=msg['content']))
            
    # Add the latest message
    langchain_messages.append(HumanMessage(content=new_user_message))
    
    # Get response from the model
    try:
        print(f"Calling Gemini with model: {llm.model}")
        response = llm.invoke(langchain_messages)
        return response.content
    except Exception as e:
        import traceback
        print(f"LangChain LLM invocation failed: {str(e)}")
        print(traceback.format_exc())
        raise e
