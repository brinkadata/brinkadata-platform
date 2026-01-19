# Brinkadata Prompt Files
# These .prompt files provide context and instructions for development in VS Code.

## How to Use
1. Open VS Code with this workspace
2. Open Copilot Chat (Ctrl+Alt+I or Cmd+Alt+I)
3. For custom instructions: Go to VS Code Settings > Extensions > GitHub Copilot Chat > Custom Instructions, and paste the content from `custom_instructions.prompt`
4. When asking Copilot for help, reference the relevant .prompt file, e.g., "Using account_management.prompt, design the User model"

## Available Prompts
- `core_context.prompt`: Overall project overview and roadmap
- `account_management.prompt`: Layer 1 - Identity & accounts
- `pricing_engine.prompt`: Layer 2 - Subscriptions & plans
- `affiliate_network.prompt`: Layer 3 - Referrals & partners
- `custom_instructions.prompt`: Copilot behavior guidelines

## Workflow
- Start with `core_context.prompt` for any new task
- Use specific prompts for feature implementation
- Implement in order: backend models → APIs → frontend
- Test changes locally (run backend with `uvicorn backend.main:app --reload`, frontend with `streamlit run frontend/app.py`)

## Migration Notes
- Current app is single-user; we're adding multi-tenancy
- Existing data needs account_id/user_id tagging
- Use mock auth for development until real login is implemented