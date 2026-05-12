#!/usr/bin/env python3
import json
import subprocess
import sys
import urllib.request
from google.cloud import discoveryengine
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

def list_discovery_engine_agents(project_id, token, engine_path, engine_location):
    """Lists custom agents created using Agent Designer within a Discovery Engine App."""
    endpoint = "https://discoveryengine.googleapis.com" if engine_location == "global" else f"https://{engine_location}-discoveryengine.googleapis.com"
    url = f"{endpoint}/v1alpha/{engine_path}/assistants/default_assistant/agents"
    
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("x-goog-user-project", project_id)
    req.add_header("Accept", "application/json")
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            agents = data.get("agents", [])
            if agents:
                print("Custom Agents (Agent Designer / Agent Gallery):")
                print("=" * 60)
                for agent in agents:
                    print(f" - Agent Name: {agent.get('displayName')}")
                    print(f"   Description: {agent.get('description', 'N/A')}")
                    print(f"   Resource Path: {agent.get('name')}\n")
                print()
                return True
    except Exception:
        pass
    return False

def list_playbooks(client, agent_path):
    try:
        request = dialogflowcx_v3.ListPlaybooksRequest(parent=agent_path)
        results = client.list_playbooks(request=request)
        playbooks = list(results)
        if playbooks:
            print("Generative Playbook Agents:")
            for pb in playbooks:
                print(f" - Name: {pb.display_name}")
                print(f"   Goal: {pb.goal}")
                print(f"   Path: {pb.name}")
                print("-" * 40)
            return True
    except Exception:
        pass
    return False

def list_flows(client, agent_path):
    try:
        request = dialogflowcx_v3.ListFlowsRequest(parent=agent_path)
        results = client.list_flows(request=request)
        flows = list(results)
        if flows:
            print("\nConversational Flow Agents:")
            for fl in flows:
                print(f" - Name: {fl.display_name}")
                print(f"   Description: {fl.description or 'N/A'}")
                print(f"   Path: {fl.name}")
                print("-" * 40)
            return True
    except Exception:
        pass
    return False

def list_app_agents(project_id, token, app_name):
    engine_path, engine_location = find_engine_by_name(project_id, app_name)
    if not engine_path:
        print(f"Error: App '{app_name}' not found.", file=sys.stderr)
        return
        
    print(f"Found App Path: {engine_path}")
    print(f"Scanning location '{engine_location}' for custom and connected agents...\n")
    
    # 1. Scan for custom Agent Designer / Agent Gallery agents
    found_designer = list_discovery_engine_agents(project_id, token, engine_path, engine_location)
    
    # 2. Scan for Dialogflow CX connected agents
    cx_locations = ["global", "us-central1", "us"]
    found_cx = False
    
    for loc in cx_locations:
        client_options = {"api_endpoint": f"{loc}-dialogflow.googleapis.com"}
        client = dialogflowcx_v3.AgentsClient(client_options=client_options)
        
        parent = f"projects/{project_id}/locations/{loc}"
        request = dialogflowcx_v3.ListAgentsRequest(parent=parent)
        
        try:
            for agent in client.list_agents(request=request):
                connected_engine = agent.gen_app_builder_settings.engine
                if connected_engine and (engine_path in connected_engine or connected_engine in engine_path):
                    found_cx = True
                    print(f"Connected Dialogflow CX Agent Container: {agent.display_name} ({agent.name})")
                    print("=" * 60)
                    
                    pb_client = dialogflowcx_v3.PlaybooksClient(client_options=client_options)
                    flows_client = dialogflowcx_v3.FlowsClient(client_options=client_options)
                    
                    list_playbooks(pb_client, agent.name)
                    list_flows(flows_client, agent.name)
        except Exception:
            pass
            
    if not found_designer and not found_cx:
        print("No custom or connected agents found for this app.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python list_app_agents.py <app_display_name_or_id>")
        print("Example: python list_app_agents.py \"hello_world\"")
        sys.exit(1)
        
    app_name = sys.argv[1]
    project_id = get_gcloud_project()
    if not project_id:
        print("Error: Could not determine active Google Cloud project ID.", file=sys.stderr)
        sys.exit(1)
        
    token = get_gcloud_access_token()
    if not token:
        print("Error: Could not retrieve active access token.", file=sys.stderr)
        sys.exit(1)
        
    list_app_agents(project_id, token, app_name)

if __name__ == "__main__":
    main()
