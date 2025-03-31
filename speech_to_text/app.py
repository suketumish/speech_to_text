from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
import speech_recognition as sr
import soundfile as sf
import tempfile
from datetime import datetime
import logging
from flask_cors import CORS
import time
from pymongo import MongoClient
from bson.objectid import ObjectId
import urllib.parse

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
CORS(app)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB
app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'ogg', 'flac', 'm4a', 'aac', 'mp4', 'mov'}
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['UPLOAD_TIMEOUT'] = 300  # 5 minutes timeout

# MongoDB Configuration
app.config['MONGO_URI'] = "mongodb://localhost:27017/"  # Update with your MongoDB URI
app.config['MONGO_DBNAME'] = "audio_transcriptions"  # Your database name

# Initialize MongoDB
def get_db():
    username = urllib.parse.quote_plus('your_username')  # If authentication is needed
    password = urllib.parse.quote_plus('your_password')
    client = MongoClient(app.config['MONGO_URI'])
    return client[app.config['MONGO_DBNAME']]

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/health')
def health_check():
    try:
        # Test MongoDB connection
        db = get_db()
        db.command('ping')
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'healthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    temp_path = None
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed'}), 400

        # Create secure temp file path
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        
        # Save file
        file.save(temp_path)
        logger.debug(f"File saved temporarily at: {temp_path}")

        # Validate file exists
        if not os.path.exists(temp_path):
            raise Exception("Failed to save uploaded file")

        # Convert to WAV if needed
        if not temp_path.lower().endswith('.wav'):
            logger.debug("Converting to WAV format...")
            wav_path = convert_to_wav(temp_path)
            os.remove(temp_path)
            temp_path = wav_path

        # Transcribe audio
        logger.debug("Starting transcription...")
        transcription = transcribe_audio(temp_path)
        logger.debug("Transcription completed")

        # Store in MongoDB
        db = get_db()
        transcription_data = {
            'filename': file.filename,
            'original_filename': file.filename,
            'transcription': transcription,
            'file_size': os.path.getsize(temp_path),
            'content_type': file.content_type,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = db.transcriptions.insert_one(transcription_data)
        transcription_id = str(result.inserted_id)

        return jsonify({
            'message': 'Success',
            'transcription': transcription,
            'filename': file.filename,
            'transcription_id': transcription_id
        })

    except Exception as e:
        logger.error(f"Error during processing: {str(e)}", exc_info=True)
        error_response = {
            'error': str(e),
            'suggestion': 'Please try a different file or shorter audio clip'
        }
        return jsonify(error_response), 500

    finally:
        # Clean up in all cases
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.error(f"Error cleaning up temp file: {str(e)}")

@app.route('/transcriptions', methods=['GET'])
def get_transcriptions():
    try:
        db = get_db()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        skip = (page - 1) * per_page
        transcriptions = list(db.transcriptions.find().sort('created_at', -1).skip(skip).limit(per_page))
        
        # Convert ObjectId to string and format dates
        for doc in transcriptions:
            doc['_id'] = str(doc['_id'])
            doc['created_at'] = doc['created_at'].isoformat()
            doc['updated_at'] = doc['updated_at'].isoformat()
        
        total = db.transcriptions.count_documents({})
        
        return jsonify({
            'transcriptions': transcriptions,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/transcriptions/<transcription_id>', methods=['GET'])
def get_transcription(transcription_id):
    try:
        db = get_db()
        doc = db.transcriptions.find_one({'_id': ObjectId(transcription_id)})
        
        if not doc:
            return jsonify({'error': 'Transcription not found'}), 404
        
        doc['_id'] = str(doc['_id'])
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        
        return jsonify(doc)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def convert_to_wav(input_path):
    """More robust audio conversion using pydub that handles video files"""
    from pydub import AudioSegment
    
    output_path = os.path.splitext(input_path)[0] + '.wav'
    
    try:
        # Check if this is a video file (MP4, MOV)
        if input_path.lower().endswith(('.mp4', '.mov')):
            # Extract audio from video
            logger.debug("Extracting audio from video file...")
            video = AudioSegment.from_file(input_path, format=input_path.split('.')[-1])
            audio = video
        else:
            # Regular audio file conversion
            audio = AudioSegment.from_file(input_path)
        
        # Standardize audio format
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(output_path, format='wav', parameters=[
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1'
        ])
        return output_path
    except Exception as e:
        raise Exception(f"Conversion failed: {str(e)}")

def transcribe_audio(audio_path):
    """Transcribe with better error handling and audio validation"""
    r = sr.Recognizer()
    
    try:
        # First validate the audio file
        with sf.SoundFile(audio_path) as f:
            duration = len(f) / f.samplerate
            if duration > 60:  # Google's limit is ~60 seconds for free API
                raise Exception("Audio too long (max 60 seconds for free API)")
            if f.samplerate < 8000 or f.samplerate > 48000:
                raise Exception(f"Unsupported sample rate: {f.samplerate}Hz (try 16kHz)")

        with sr.AudioFile(audio_path) as source:
            # Read the entire file (for short files) or in chunks (for longer files)
            if duration <= 60:
                audio = r.record(source)
            else:
                # For longer files, process in chunks
                audio = r.record(source, duration=60)
                logger.warning("Only processing first 60 seconds due to API limits")
            
            # Try recognition with multiple attempts
            for attempt in range(3):
                try:
                    return r.recognize_google(
                        audio,
                        language='en-US',
                        show_all=False
                    )
                except sr.UnknownValueError:
                    if attempt == 2:
                        return "Could not understand audio"
                    time.sleep(1)  # Wait before retrying
                except sr.RequestError as e:
                    if attempt == 2:
                        raise Exception(f"Google API error: {str(e)}")
                    time.sleep(1)
    
    except Exception as e:
        raise Exception(f"Audio processing error: {str(e)}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)