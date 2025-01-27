from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, cast
import asyncio
import uuid
import json
from datetime import datetime

from .security.api_key import api_key_manager, get_api_key

from src.utils.default_config_settings import load_config_from_file, default_config
from src.agent.custom_agent import CustomAgent
from src.browser.custom_browser import CustomBrowser
from src.controller.custom_controller import CustomController
from src.utils.utils import get_llm_model
from src.utils.agent_state import AgentState
from browser_use.browser.browser import BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig, BrowserContextWindowSize

app = FastAPI(
    title="Browser Use API",
    description="API for browser automation with built-in security",
    version="1.0.0"
)

# API Key management endpoints
class APIKeyResponse(BaseModel):
    key: str
    expires_at: str
    created_at: str

class APIKeyInfo(BaseModel):
    expires_at: datetime
    created_at: datetime
    is_active: bool
    last_used: Optional[datetime]
    usage_count: int

class ActiveKeysResponse(BaseModel):
    keys: Dict[str, APIKeyInfo]

@app.post("/api-keys/generate", response_model=APIKeyResponse)
async def generate_api_key(expires_in_days: Optional[int] = 30):
    """Generate a new API key"""
    try:
        key = api_key_manager.generate_key(expires_in_days)
        key_info = api_key_manager.get_key_info(key)
        if not key_info:
            raise HTTPException(status_code=500, detail="Failed to generate API key")
        
        return APIKeyResponse(
            key=key,
            expires_at=key_info["expires_at"].isoformat(),
            created_at=key_info["created_at"].isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api-keys/rotate")
async def rotate_api_key(current_api_key: str = Security(get_api_key)):
    """Rotate an existing API key"""
    try:
        new_key = api_key_manager.rotate_key(current_api_key)
        if not new_key:
            raise HTTPException(status_code=400, detail="Failed to rotate API key")
        
        key_info = api_key_manager.get_key_info(new_key)
        if not key_info:
            raise HTTPException(status_code=500, detail="Failed to get new key info")
        
        return APIKeyResponse(
            key=new_key,
            expires_at=key_info["expires_at"].isoformat(),
            created_at=key_info["created_at"].isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api-keys/revoke")
async def revoke_api_key(api_key: str = Security(get_api_key)):
    """Revoke an API key"""
    if api_key_manager.revoke_key(api_key):
        return {"message": "API key revoked successfully"}
    raise HTTPException(status_code=400, detail="Failed to revoke API key")

@app.get("/api-keys/active", response_model=ActiveKeysResponse)
async def list_active_keys(api_key: str = Security(get_api_key)):
    """List all active API keys"""
    try:
        active_keys = api_key_manager.list_active_keys()
        return ActiveKeysResponse(keys=active_keys)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list active keys: {str(e)}")

# Store for active tasks and their results
tasks_store: Dict[str, Dict[str, Any]] = {}

class TaskRequest(BaseModel):
    task: str
    add_infos: Optional[str] = ""
    config_file: Optional[str] = None  # Path to custom config file
    # Direct configuration options
    llm_model_name: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_temperature: Optional[float] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    max_steps: Optional[int] = None
    max_actions_per_step: Optional[int] = None
    use_vision: Optional[bool] = None
    headless: Optional[bool] = None

class TaskResponse(BaseModel):
    task_id: str
    status: str
    created_at: str

class TaskResult(BaseModel):
    task_id: str
    status: str
    final_result: Optional[str] = None
    errors: Optional[str] = None
    model_actions: Optional[str] = None
    model_thoughts: Optional[str] = None
    recording_path: Optional[str] = None
    trace_file: Optional[str] = None
    history_file: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

async def execute_task(task_id: str, task_request: TaskRequest):
    try:
        # Load base configuration
        if task_request.config_file:
            config = load_config_from_file(task_request.config_file)
            if isinstance(config, str):  # Error case
                raise ValueError(f"Failed to load config file: {config}")
        else:
            config = default_config()

        # Ensure config is a dictionary
        if not isinstance(config, dict):
            raise ValueError("Invalid configuration format")

        # Override with any directly specified config values
        config_updates = {
            k: v for k, v in {
                'llm_model_name': task_request.llm_model_name,
                'llm_provider': task_request.llm_provider,
                'llm_temperature': task_request.llm_temperature,
                'llm_base_url': task_request.llm_base_url,
                'llm_api_key': task_request.llm_api_key,
                'max_steps': task_request.max_steps,
                'max_actions_per_step': task_request.max_actions_per_step,
                'use_vision': task_request.use_vision,
                'headless': task_request.headless
            }.items() if v is not None
        }
        config.update(config_updates)

        # Initialize LLM with type-safe config access
        config_dict = cast(Dict[str, Any], config)
        llm = get_llm_model(
            provider=str(config_dict.get('llm_provider', 'openai')),
            model_name=str(config_dict.get('llm_model_name', 'gpt-3.5-turbo')),
            temperature=float(config_dict.get('llm_temperature', 0.7)),
            base_url=config_dict.get('llm_base_url'),
            api_key=config_dict.get('llm_api_key'),
        )

        # Initialize browser with type-safe config access
        config_dict = cast(Dict[str, Any], config)
        browser = CustomBrowser(
            config=BrowserConfig(
                headless=bool(config_dict.get('headless', True)),
                disable_security=bool(config_dict.get('disable_security', False)),
                chrome_instance_path=config_dict.get('chrome_path'),
                extra_chromium_args=[f"--window-size={int(config_dict['window_w'])},{int(config_dict['window_h'])}"],
            )
        )

        browser_context = await browser.new_context(
            config=BrowserContextConfig(
                trace_path=config_dict.get('save_trace_path'),
                save_recording_path=config_dict.get('save_recording_path') if config_dict.get('enable_recording') else None,
                no_viewport=False,
                browser_window_size=BrowserContextWindowSize(
                    width=int(config_dict['window_w']),
                    height=int(config_dict['window_h'])
                ),
            )
        )

        # Initialize agent with type-safe config access
        agent = CustomAgent(
            task=task_request.task,
            add_infos=task_request.add_infos or "",
            llm=llm,
            use_vision=bool(config_dict.get('use_vision', True)),
            browser=browser,
            browser_context=browser_context,
            controller=CustomController(),
            max_actions_per_step=int(config_dict.get('max_actions_per_step', 10)),
            tool_call_in_content=bool(config_dict.get('tool_call_in_content', True)),
            agent_state=AgentState()
        )

        # Run agent with type-safe config access
        history = await agent.run(max_steps=int(config_dict.get('max_steps', 100)))

        # Save results with type-safe config access
        tasks_store[task_id].update({
            'status': 'completed',
            'final_result': json.dumps(history.final_result()) if isinstance(history.final_result(), dict) else str(history.final_result()),
            'errors': "\n".join(json.dumps(error) if isinstance(error, dict) else str(error) for error in history.errors()) if isinstance(history.errors(), list) else str(history.errors()),
'model_actions': "\n".join(json.dumps(action) if isinstance(action, dict) else str(action) for action in history.model_actions()) if isinstance(history.model_actions(), list) else str(history.model_actions()),
'model_thoughts': "\n".join(json.dumps(thought) if isinstance(thought, dict) else str(thought) for thought in history.model_thoughts()) if isinstance(history.model_thoughts(), list) else str(history.model_thoughts()),
            'recording_path': config_dict.get('save_recording_path') if config_dict.get('enable_recording') else None,
            'trace_file': config_dict.get('save_trace_path'),
            'history_file': f"{config_dict.get('save_agent_history_path', 'tmp/agent_history')}/{agent.agent_id}.json",
            'config': config_dict
        })

    except Exception as e:
        tasks_store[task_id].update({
            'status': 'failed',
            'errors': str(e)
        })
    finally:
        if not bool(config_dict.get('keep_browser_open', False)):
            if browser_context:
                await browser_context.close()
            if browser:
                await browser.close()

@app.post("/tasks", response_model=TaskResponse, dependencies=[Depends(get_api_key)])
async def create_task(task_request: TaskRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks_store[task_id] = {
        'status': 'pending',
        'created_at': datetime.utcnow().isoformat(),
        'final_result': None,
        'errors': None,
        'model_actions': None,
        'model_thoughts': None,
        'recording_path': None,
        'trace_file': None,
        'history_file': None,
        'config': None
    }
    
    background_tasks.add_task(execute_task, task_id, task_request)
    
    return TaskResponse(
        task_id=task_id,
        status='pending',
        created_at=tasks_store[task_id]['created_at']
    )

@app.get("/tasks/{task_id}", response_model=TaskResult, dependencies=[Depends(get_api_key)])
async def get_task_result(task_id: str):
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskResult(
        task_id=task_id,
        **tasks_store[task_id]
    )

@app.get("/tasks", response_model=List[TaskResult], dependencies=[Depends(get_api_key)])
async def list_tasks():
    return [
        TaskResult(task_id=task_id, **task_data)
        for task_id, task_data in tasks_store.items()
    ]
