from flask import Flask, request, jsonify, render_template
import openai
import logging
import base64
import requests
from google.cloud import speech
import os
import wave
import io
import cloudconvert

# Set up OpenAI API key
openai.api_key = 'sk-proj-F704f85CQc38Zr2ooHxgT3BlbkFJecXaYYRs9pO5fMO1Vkq8'
OPENAI_API_KEY = 'sk-proj-F704f85CQc38Zr2ooHxgT3BlbkFJecXaYYRs9pO5fMO1Vkq8'

# Set the environment variable for Google Cloud credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/home/joshuaaa510/stt_key.json'

# Initialize CloudConvert API with new key
cloudconvert_api_key = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiNjBkNDY4MDVkMDdjOThkN2Y3NWQ0Y2Y1YzIxNDY2NDM5MzEwNDNjNjk4M2NkMmE3ZDJkYzA1ZmMxNmEwYmEyMzgzOGU4MGUxOGViOTI4N2EiLCJpYXQiOjE3MTgwNDA4ODguMDIxNzc2LCJuYmYiOjE3MTgwNDA4ODguMDIxNzc3LCJleHAiOjQ4NzM3MTQ0ODguMDE3NTUyLCJzdWIiOiI2ODY2MTMxNyIsInNjb3BlcyI6WyJwcmVzZXQud3JpdGUiLCJwcmVzZXQucmVhZCIsIndlYmhvb2sud3JpdGUiLCJ3ZWJob29rLnJlYWQiLCJ0YXNrLndyaXRlIiwidGFzay5yZWFkIiwidXNlci53cml0ZSIsInVzZXIucmVhZCJdfQ.QEwWv7ws2C2X0pe1bQJkL9nLZDeMYKPnMhVlJSY4p_otqyx9qen8LbRh7FcBNW9ak_05gGPdobacLYt-Slwb60ZlfJUZvNzLVe6XLhZgjLW9tilI15SDa_Wz6aW7V7XpOGkJB2JOxf8PfRE2K7hHFe9lc6fO9kP9EzyAynN61fGYwopwXKRWKLXUC9efPjvHqT3lt9ZJBw_hOnW7g3nW7kp3ykAYlCpGKeyiw6ONqwKbSnsUfDIOMluADS1oRJxNDZweO2owT5qDaqfPGLLF36EPKpDXvq7D5LrdYO_N3J7uvzrWj1fFWv2bZHmETJJ5lsZUaSvuCuPb_mOcJPVHQKDI3RsoNA7cZv7K4ZD6Jp0Szzqs0WjMeZcGlhY419CBc8p5TRiEsN6sgz-JT5OIYDwNPCLTT5gViqn-mgNS6wtQvbk-ExW6hnJC9F4UVB7BkHECp-j0L_rsyrXyIxTnqfzZMzdzp6rVe5k3vQpYo69RF5a4AD01cBbofP2yNNlTFvewAaTzS0i3A_RCNvcsj4PgjPgX-My-UkzPEZSmOaXyO9CkksTo06K__9YeqWBA8CEjzmvSS79t_HpKiMD0TS3itnGDG8jIEoe2rpPecZBYApxFyJLMskOYl33FFTsGs-5aLqtkIFNZUBwGBuQ6huXQqCB8HgSuwrqxL0TEdhc'
cloudconvert.configure(api_key=cloudconvert_api_key)

app = Flask(__name__)

# Set up logging to file
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(message)s')

conversation_history = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        logging.debug("Received request at /chat")
        user_message = request.json.get('message')
        logging.debug(f"User message: {user_message}")

        # Update conversation history
        conversation_history.append({"role": "user", "content": user_message})
        if len(conversation_history) > 10:  # Limit context to last 10 exchanges
            conversation_history.pop(0)

        # Generate a response using OpenAI with system instructions and conversation history
        system_instructions = (
            'You are Sara, a highly intelligent and personable customer service representative at Toyota Marin. '
            'Your goal is to provide helpful and concise information about Toyota vehicles, book appointments, and gather customers\' names and numbers. '
            'Make sure to keep your responses short and directly related to the customer\'s query. '
            'Engage in friendly banter to make the conversation enjoyable, but avoid repeating the same phrases. '
            'Use "uh" and "um" occasionally to sound more human-like. '
            'Remember past interactions to maintain context and coherence in the conversation. '
            'Be witty, charming, and humorous, but prioritize clear and helpful information.'
        )

        messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_message}
        ] + conversation_history

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        response_text = response.choices[0].message['content'].strip()
        conversation_history.append({"role": "assistant", "content": response_text})

        audio_response = synthesize_speech(response_text)
        logging.debug(f"OpenAI response text: {response_text}")
        logging.debug(f"Generated audio length: {len(audio_response) if audio_response else 'None'} bytes")

        return jsonify({
            "text": response_text,
            "audio": audio_response.decode('utf-8') if audio_response else None
        })
    except Exception as e:
        logging.error(f"Error processing request: {e}", exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500

@app.route('/audio', methods=['POST'])
def audio():
    try:
        logging.debug("Received audio request at /audio")
        audio_file = request.files['file']
        audio_content = audio_file.read()
        logging.debug(f"Received audio content length: {len(audio_content)} bytes")

        # Use Google Cloud Speech-to-Text for transcription
        transcription = transcribe_audio(audio_content, audio_file.filename)
        user_message = transcription['text']
        logging.debug(f"Transcribed user message: {user_message}")

        # Update conversation history with transcribed message
        conversation_history.append({"role": "user", "content": user_message})
        if len(conversation_history) > 10:  # Limit context to last 10 exchanges
            conversation_history.pop(0)

        # Generate a response using OpenAI with system instructions and conversation history
        system_instructions = (
            'You are Sara, a highly intelligent and personable customer service representative at Toyota Marin. '
            'Your goal is to provide helpful and concise information about Toyota vehicles, book appointments, and gather customers\' names and numbers. '
            'Make sure to keep your responses short and directly related to the customer\'s query. '
            'Engage in friendly banter to make the conversation enjoyable, but avoid repeating the same phrases. '
            'Use "uh" and "um" occasionally to sound more human-like. '
            'Remember past interactions to maintain context and coherence in the conversation. '
            'Be witty, charming, and humorous, but prioritize clear and helpful information.'
        )

        messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_message}
        ] + conversation_history

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        response_text = response.choices[0].message['content'].strip()
        conversation_history.append({"role": "assistant", "content": response_text})

        audio_response = synthesize_speech(response_text)
        logging.debug(f"OpenAI response text: {response_text}")
        logging.debug(f"Generated audio length: {len(audio_response) if audio_response else 'None'} bytes")

        return jsonify({
            "message": user_message,
            "response": {
                "text": response_text,
                "audio": audio_response.decode('utf-8') if audio_response else None
            }
        })
    except Exception as e:
        logging.error(f"Error processing audio request: {e}", exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500

def synthesize_speech(text):
    try:
        headers = {
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json',
        }
        json_data = {
            'model': 'tts-1',
            'voice': 'shimmer',
            'input': text,
        }
        response = requests.post('https://api.openai.com/v1/audio/speech', headers=headers, json=json_data)
        if response.status_code == 200:
            audio_content = response.content
            return base64.b64encode(audio_content)
        else:
            logging.error(f"Error from TTS API: {response.status_code}, {response.text}")
            return None
    except Exception as e:
        logging.error(f"Error synthesizing speech: {e}", exc_info=True)
        return None

def get_audio_properties(audio_content, file_extension):
    audio_file = io.BytesIO(audio_content)
    if file_extension == 'wav':
        with wave.open(audio_file, 'rb') as wave_file:
            sample_rate_hertz = wave_file.getframerate()
            channels = wave_file.getnchannels()
            return sample_rate_hertz, channels
    elif file_extension == 'flac':
        return 48000, 2  # Common sample rate and channel count for FLAC files
    elif file_extension == 'mp3':
        return 44100, 2  # Common sample rate and channel count for MP3 files
    elif file_extension == 'webm':
        return 16000, 1  # Default sample rate and channel count for WebM files
    else:
        return 16000, 1  # Default sample rate and channel count

def convert_audio_to_wav(audio_content, original_format):
    try:
        with open(f'temp.{original_format}', 'wb') as f:
            f.write(audio_content)
        job = cloudconvert.Job.create(payload={
            "tasks": {
                "import-my-file": {
                    "operation": "import/upload"
                },
                "convert-my-file": {
                    "operation": "convert",
                    "input": "import-my-file",
                    "output_format": "wav"
                },
                "export-my-file": {
                    "operation": "export/url",
                    "input": "convert-my-file"
                }
            }
        })
        upload_task_id = job['tasks'][0]['id']

        # Perform the upload with the correct method
        upload_task = cloudconvert.Task.find(id=upload_task_id)
        cloudconvert.Task.upload(file_name=f'temp.{original_format}', task=upload_task)

        export_task_id = job['tasks'][2]['id']
        result = cloudconvert.Task.wait(id=export_task_id)

        if result and 'result' in result and 'files' in result['result'] and result['result']['files']:
            file_url = result['result']['files'][0]['url']
            response = requests.get(file_url)
            return response.content
        else:
            logging.error("Failed to get the converted file URL from CloudConvert.")
            return None
    except Exception as e:
        logging.error(f"Error converting audio to wav: {e}", exc_info=True)
        return None

def transcribe_audio(audio_content, filename):
    try:
        file_extension = filename.split('.')[-1].lower()
        if file_extension in ['m4a', 'webm']:
            audio_content = convert_audio_to_wav(audio_content, file_extension)
            if audio_content is None:
                return {"text": ""}  # Return an empty transcription if conversion fails
            file_extension = 'wav'  # Treat it as WAV after conversion

        sample_rate_hertz, audio_channel_count = get_audio_properties(audio_content, file_extension)

        if file_extension == 'flac':
            encoding = speech.RecognitionConfig.AudioEncoding.FLAC
        elif file_extension == 'mp3':
            encoding = speech.RecognitionConfig.AudioEncoding.MP3
        elif file_extension == 'wav':
            encoding = speech.RecognitionConfig.AudioEncoding.LINEAR16
        else:
            logging.error("Unsupported audio format")
            return {"text": ""}

        logging.debug(f"Using encoding: {encoding}, sample rate hertz: {sample_rate_hertz}, channels: {audio_channel_count}")

        # Set up Google Cloud Speech client
        client = speech.SpeechClient()

        # Configure audio and recognition settings
        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=sample_rate_hertz,
            audio_channel_count=audio_channel_count,
            language_code="en-US",
        )

        # Perform the transcription
        response = client.recognize(config=config, audio=audio)

        # Log the full response from Google Cloud STT
        logging.debug(f"Google STT response: {response}")

        # Collect the transcription results
        transcription = ""
        for result in response.results:
            transcription += result.alternatives[0].transcript

        logging.debug(f"Transcription: {transcription}")

        return {"text": transcription}
    except Exception as e:
        logging.error(f"Error transcribing audio: {e}", exc_info=True)
        return {"text": ""}

if __name__ == '__main__':
    app.run(port=36637, debug=True)
