import os
import sys
from pathlib import Path

# Add the root directory to sys.path to allow imports if needed
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    from bot_admin import main
    main()
