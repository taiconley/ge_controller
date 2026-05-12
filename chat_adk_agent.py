#!/usr/bin/env python3
import json
import sys
import uuid
import subprocess
import urllib.request
from google.cloud import discoveryengine_v1 as discoveryengine
from google.cloud import dialogflowcx_v3

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
    """Fetches details of a custom agent by display name inside an app."""
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

def chat_with_cx_agent(project_id, agent_path, loc, user_message):
    """Interacts with a standard Dialogflow CX agent."""
    client_options = {"api_endpoint": f"{loc}-dialogflow.googleapis.com"}
    client = dialogflowcx_v3.SessionsClient(client_options=client_options)
    
    session_id = str(uuid.uuid4())
    session_path = f"{agent_path}/sessions/{session_id}"
    
    text_input = dialogflowcx_v3.TextInput(text=user_message)
    query_input = dialogflowcx_v3.QueryInput(text=text_input, language_code="en")
    
    request = dialogflowcx_v3.DetectIntentRequest(
        session=session_path,
        query_input=query_input
    )
    
    try:
        response = client.detect_intent(request=request)
        for message in response.query_result.response_messages:
            if message.text:
                print(f"Agent: {message.text.text[0]}")
    except Exception as e:
        print(f"Error chatting with CX agent: {e}", file=sys.stderr)

def chat_with_a2a_agent(a2a_url, user_message):
    """Converses directly with a custom A2A agent using standard JSON-RPC over HTTPS."""
    # Generate unique IDs for session/message tracking
    session_id = f"thread-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    
    payload = {
        "jsonrpc": "2.0",
        "id": "req-001",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [{"kind": "text", "text": user_message}],
                "contextId": session_id
            }
        }
    }
    
    req = urllib.request.Request(
        a2a_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if "error" in res_data:
                print(f"Agent error: {res_data['error'].get('message')}", file=sys.stderr)
                return
            
            history = res_data.get("result", {}).get("history", [])
            
            # Locate the final agent text reply in the output task history
            found = False
            for item in reversed(history):
                if item.get("role") == "agent":
                    for part in item.get("parts", []):
                        if part.get("kind") == "text":
                            print(f"Agent: {part.get('text')}")
                            found = True
                            break
                if found:
                    break
            if not found:
                print("Agent invoked successfully, but returned no text reply.")
    except Exception as e:
        print(f"Error communicating with A2A agent: {e}", file=sys.stderr)

def main():
    if len(sys.argv) < 4:
        print("Usage: python chat.py <app_name> <agent_name> <message>")
        print("Example: python chat.py \"hello_world\" \"hello_agent\" \"hello\"")
        sys.exit(1)
        
    app_name = sys.argv[1]
    agent_name = sys.argv[2]
    user_message = sys.argv[3]
    
    project_id = get_gcloud_project()
    if not project_id:
        print("Error: Could not determine active Google Cloud project ID.", file=sys.stderr)
        sys.exit(1)
        
    token = get_gcloud_access_token()
    if not token:
        print("Error: Could not retrieve active access token.", file=sys.stderr)
        sys.exit(1)
        
    engine_path, loc = find_engine_by_name(project_id, app_name)
    if not engine_path:
        print(f"Error: App '{app_name}' not found.", file=sys.stderr)
        sys.exit(1)
        
    # 1. Check if it is a custom Agent Designer agent under the app
    agent_details = get_agent_details(project_id, token, loc, engine_path, agent_name)
    if agent_details:
        a2a_def = agent_details.get("a2aAgentDefinition", {})
        if a2a_def:
            # It is an A2A Agent running on Cloud Run! Converse directly using Agent2Agent protocol.
            try:
                card_data = json.loads(a2a_def.get("jsonAgentCard", "{}"))
                # Extract the project number from the agent's full resource name (segment index 1)
                project_number = agent_details.get("name").split("/")[1]
                a2a_url = f"https://hello-agent-{project_number}.us-central1.run.app/"
                chat_with_a2a_agent(a2a_url, user_message)
                return
            except Exception as e:
                print(f"Failed to establish A2A connection: {e}", file=sys.stderr)
                return
        else:
            # Natively hosted Agent Designer node (LowCodeAgent)
            print("This custom agent is natively hosted in Agent Studio.")
            print("Use the Google Cloud Console interface to interact with low-code agents.")
            return

    # 2. Check if it is a standard Dialogflow CX agent
    cx_locations = ["global", "us-central1", "us"]
    cx_agent_path = None
    cx_agent_loc = None
    
    for cx_loc in cx_locations:
        client_options = {"api_endpoint": f"{cx_loc}-dialogflow.googleapis.com"}
        client = dialogflowcx_v3.AgentsClient(client_options=client_options)
        parent = f"projects/{project_id}/locations/{cx_loc}"
        
        try:
            for agent in client.list_agents(request=parent):
                if agent.display_name == agent_name:
                    connected_engine = agent.gen_app_builder_settings.engine
                    if connected_engine and (engine_path in connected_engine or connected_engine in engine_path):
                        cx_agent_path = agent.name
                        cx_agent_loc = cx_loc
                        break
        except Exception:
            pass
            
    if cx_agent_path:
        chat_with_cx_agent(project_id, cx_agent_path, cx_agent_loc, user_message)
    else:
        print(f"Error: No custom or connected agent named '{agent_name}' found for app '{app_name}'.")

if __name__ == "__main__":
    main()
