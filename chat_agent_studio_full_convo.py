#!/usr/bin/env python3
import json
import sys
import subprocess
import urllib.request
from google.cloud import discoveryengine_v1 as discoveryengine

def get_gcloud_project():
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return None

def get_gcloud_access_token():
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return None

def find_engine_by_name(project_id, app_name):
    locations = ["global", "us"]
    for loc in locations:
        client_options = {}
        if loc != "global":
            client_options = {"api_endpoint": f"{loc}-discoveryengine.googleapis.com"}
        client = discoveryengine.EngineServiceClient(client_options=client_options)
        parent = f"projects/{project_id}/locations/{loc}/collections/default_collection"
        
        request = discoveryengine.ListEnginesRequest(parent=parent)
        try:
            for engine in client.list_engines(request=request):
                if engine.display_name == app_name or app_name in engine.name:
                    return engine.name, loc
        except Exception:
            pass
    return None, None

def get_agent_details(project_id, token, loc, engine_path, agent_name):
    endpoint = "https://discoveryengine.googleapis.com" if loc == "global" else f"https://{loc}-discoveryengine.googleapis.com"
    url = f"{endpoint}/v1alpha/{engine_path}/assistants/default_assistant/agents"
    
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("x-goog-user-project", project_id)
    req.add_header("Accept", "application/json")
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            agents = data.get("agents", [])
            for agent in agents:
                if agent.get("displayName") == agent_name or agent_name in agent.get("name"):
                    return agent
    except Exception:
        pass
    return None

def send_message_and_stream_response(client, assistant_name, session_urn, message):
    request = discoveryengine.StreamAssistRequest(
        name=assistant_name,
        query=discoveryengine.Query(text=message),
        session=session_urn
    )
    
    try:
        stream = client.stream_assist(request=request)
        found_reply = False
        
        for response in stream:
            if hasattr(response, "answer") and response.answer:
                for reply in response.answer.replies:
                    if reply.grounded_content and reply.grounded_content.content:
                        # Filter out reasoning/thoughts, only print model text answers
                        is_thought = reply.grounded_content.content.thought
                        text = reply.grounded_content.content.text
                        if text and not is_thought:
                            print(text, end="", flush=True)
                            found_reply = True
        
        if found_reply:
            print()
        else:
            print("Agent successfully invoked, but did not return any text output.")
    except Exception as e:
        print(f"Error conversing with Agent Studio agent: {e}", file=sys.stderr)

def chat_with_studio_agent(project_id, token, app_name, agent_name, initial_message=None):
    engine_path, loc = find_engine_by_name(project_id, app_name)
    if not engine_path:
        print(f"Error: App '{app_name}' not found.", file=sys.stderr)
        return
        
    agent_details = get_agent_details(project_id, token, loc, engine_path, agent_name)
    if not agent_details:
        print(f"Error: Agent '{agent_name}' not found.", file=sys.stderr)
        return
        
    low_code_def = agent_details.get("lowCodeAgentDefinition", {})
    if not low_code_def:
        print(f"Error: Agent '{agent_name}' is not a natively hosted Agent Studio low-code agent.", file=sys.stderr)
        return
        
    # Extract the pre-warmed session URN assigned to the agent
    session_path_segment = low_code_def.get("session")
    if not session_path_segment:
        print(f"Error: No active session URN configured for Agent '{agent_name}'.", file=sys.stderr)
        return
        
    # Build full session URN path
    project_number = engine_path.split("/")[1]
    session_urn = f"projects/{project_number}/locations/{loc}/{session_path_segment}"
    
    # Configure the Assistant client
    client_options = {}
    if loc != "global":
        client_options = {"api_endpoint": f"{loc}-discoveryengine.googleapis.com"}
    client = discoveryengine.AssistantServiceClient(client_options=client_options)
    
    assistant_name = f"{engine_path}/assistants/default_assistant"
    
    print(f"Routing conversation to custom session: {session_urn}\n")
    
    if initial_message:
        send_message_and_stream_response(client, assistant_name, session_urn, initial_message)
    
    while True:
        try:
            user_input = input("\nUser: ").strip()
            if user_input.lower() in ['exit', 'quit']:
                print("Exiting conversation.")
                break
            if not user_input:
                continue
                
            print() # Add a newline before agent response for clean spacing
            send_message_and_stream_response(client, assistant_name, session_urn, user_input)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting conversation.")
            break

def main():
    if len(sys.argv) < 3:
        print("Usage: python chat_agent_studio_full_convo.py <app_name> <agent_name> [initial_message]")
        print("Example: python chat_agent_studio_full_convo.py \"gemini-enterprise-1777951509833\" \"Grumpy Greeter Agent\" \"Can you greet me?\"")
        sys.exit(1)
        
    app_name = sys.argv[1]
    agent_name = sys.argv[2]
    user_message = sys.argv[3] if len(sys.argv) >= 4 else None
    
    project_id = get_gcloud_project()
    if not project_id:
        print("Error: Could not determine active Google Cloud project ID.", file=sys.stderr)
        sys.exit(1)
        
    token = get_gcloud_access_token()
    if not token:
        print("Error: Could not retrieve active access token.", file=sys.stderr)
        sys.exit(1)
        
    chat_with_studio_agent(project_id, token, app_name, agent_name, user_message)

if __name__ == "__main__":
    main()
