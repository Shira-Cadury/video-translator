# 🎬 Video Translator & Subtitle Generator

A Python-based backend system that automatically generates subtitles and translations for videos.

The system downloads video audio, performs speech-to-text transcription, and generates subtitle files automatically.
The long-term goal of the project is to support translation between multiple languages, with highly accurate Hebrew translation.

---

# 🚀 Features

Current features:

* Download video audio from YouTube
* Automatic speech-to-text transcription
* Subtitle generation pipeline (in progress)

Planned features:

* Translation between multiple languages
* High-quality Hebrew translation
* Video summarization for educational content
* Web interface for uploading videos
* Support for both YouTube links and uploaded video files
* Job queue for processing multiple videos

---

# 🧠 System Workflow

```text
Video Input
     │
     ├─ YouTube URL
     └─ (Planned) Uploaded Video File
           │
           ▼
     Audio Extraction
           │
           ▼
 Speech-to-Text Transcription
           │
           ▼
     Subtitle Generator
           │
           ▼
        .srt File
```

---

# 🏗 Project Architecture

The project is built using a modular service-based architecture.

Each major responsibility is implemented as a separate service.

Example services:

* VideoService – handles video downloading
* TranscriptionService – handles speech-to-text processing
* SubtitleService – generates subtitle files

---

# 📂 Project Structure

```
video-translator
│
├── app
│   ├── api
│   ├── services
│   │   ├── video_service.py
│   │   └── transcription_service.py
│   └── utils
│
├── storage
│   ├── audio
│   └── subtitles
│
├── main.py
└── README.md
```

---

# ⚙ Technologies Used

* Python
* Whisper (Speech Recognition)
* yt-dlp (Video Download)
* FFmpeg (Audio Processing)

---

# 🛠 Installation

Clone the repository:

```
git clone <repository-url>
```

Navigate to the project directory:

```
cd video-translator
```

Create a virtual environment:

```
python -m venv venv
```

Activate the environment:

Windows:

```
venv\Scripts\activate
```

Mac/Linux:

```
source venv/bin/activate
```

Install dependencies:

```
pip install -r requirements.txt
```

---

# ▶ Running the Project

Run the system using:

```
python main.py
```

The program will:

1. Download audio from a video
2. Transcribe the audio
3. Generate text output

---

# 📌 Current Progress

Implemented:

* Video audio download
* Speech-to-text transcription

In progress:

* Subtitle file generation

Planned:

* Translation system
* Web interface
* Public deployment

---

# 🔮 Future Improvements

* Multi-language translation
* Hebrew optimized translation
* Video summarization
* Web interface for users
* Job queue for handling multiple videos
* Cloud deployment

---

# 👩‍💻 Author

Software Engineering Student Project
