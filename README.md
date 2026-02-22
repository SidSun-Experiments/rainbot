# Rainbot

Rainbot is a personalized Telegram Bot designed to download and stream audio from YouTube directly to a host machine. It utilizes `yt-dlp` for downloading and `mpv` for media playback, providing a seamless way to play music or podcasts from YouTube links via Telegram commands.

## Features

- **Direct YouTube Downloads**: Send a YouTube link to the bot, and it will automatically download the audio and start playing it.
- **Media Controls**: Play, pause, and adjust the volume of the audio directly from Telegram.
- **Library Management**: List your recently downloaded files and play them directly by clicking inline buttons.
- **Access Control**: Restrict bot usage to specific Telegram user IDs to keep it private.
- **Auto-Update**: Built-in command to keep `yt-dlp` updated to the latest version.
- **Systemd Integration**: Comes with a systemd service file for running as a background daemon.

## Prerequisites

- Python 3.8+
- `mpv` installed on the host machine.
- `yt-dlp` installed or placed in the expected directory.
- `curl` (for updating yt-dlp).

## Installation

1. **Clone the repository or copy the project files:**
   Ensure all files (`rainbot.py`, `start.sh`, `requirements.txt`, etc.) are in your project directory.

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv pyenv
   source pyenv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure the environment:**
   Copy the example environment file and edit it to include your Telegram bot token and your Telegram User ID(s).
   ```bash
   cp .env.example .env
   nano .env
   ```

4. **Adjust paths (if necessary):**
   The project assumes certain paths like `/home/sids/stacks/rainbot/`. Make sure to update the paths in `rainbot.py`, `start.sh`, and `rainbot.service` according to your actual setup.

## Usage

### Running manually
You can start the bot by running the `start.sh` script:
```bash
./start.sh
```

### Running as a Systemd Service
To ensure Rainbot runs in the background and starts on boot:
1. Update paths in `rainbot.service`.
2. Copy the service file to systemd's user directory:
   ```bash
   cp rainbot.service ~/.config/systemd/user/
   ```
3. Enable and start the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable rainbot.service
   systemctl --user start rainbot.service
   ```

## Bot Commands

Once the bot is running, interact with it on Telegram using the following commands:

- **Send a YouTube URL**: The bot will download the audio and play it automatically.
- `/play` - Resume playback
- `/pause` - Pause playback
- `/volup [amount]` - Increase volume (default: 10)
- `/voldown [amount]` - Decrease volume (default: 10)
- `/list` - List up to 20 recently downloaded files with inline buttons to play them.
- `/update` - Update `yt-dlp` to the latest release seamlessly.
- `/help` - Show the help message.
