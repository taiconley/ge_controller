#!/usr/bin/env python3
import subprocess
import sys
from google.cloud import discoveryengine

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

def list_apps(project_id: str, location: str = "global"):
    client_options = {}
    if location != "global":
        client_options = {"api_endpoint": f"{location}-discoveryengine.googleapis.com"}
        
    client = discoveryengine.EngineServiceClient(client_options=client_options)
    parent = f"projects/{project_id}/locations/{location}/collections/default_collection"
    
    request = discoveryengine.ListEnginesRequest(parent=parent)
    try:
        results = client.list_engines(request=request)
        print(f"Gemini Enterprise Apps in location '{location}':")
        print("=" * 50)
        found = False
        for engine in results:
            found = True
            print(f"App Name: {engine.display_name}")
            print(f"App Resource ID: {engine.name}\n")
        if not found:
            print("No apps found.\n")
    except Exception:
        pass

def main():
    project_id = get_gcloud_project()
    if not project_id:
        print("Error: Could not determine active Google Cloud project ID.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Active Project: {project_id}\n")
    list_apps(project_id, "global")
    list_apps(project_id, "us")

if __name__ == "__main__":
    main()
