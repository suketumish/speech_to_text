# Audio Transcription Service

A Flask-based web application that converts audio files (including MP3, WAV, MP4) to text using speech recognition and stores results in MongoDB.

![Project Screenshot](/screenshot.png) <!-- Add a screenshot if available -->

## Features

- 🎤 Supports multiple audio formats: WAV, MP3, OGG, FLAC, M4A, AAC, MP4, MOV
- 📝 Converts audio to text using Google Speech Recognition API
- 🎥 Extracts audio from video files (MP4, MOV) for transcription
- 💾 Stores transcription results in MongoDB for future reference
- 📱 Responsive web interface with drag-and-drop file upload
- 📊 Progress tracking during file upload and processing

## Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.8+
- MongoDB (local or remote instance)
- FFmpeg (for audio conversion)
- Google API key (for speech recognition)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/audio-transcription-service.git
   cd audio-transcription-service
