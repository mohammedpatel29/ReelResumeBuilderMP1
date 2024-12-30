from flask import Blueprint, jsonify, request, current_app, render_template
from flask_login import login_required, current_user
from models import ResumeAnalysis, db
import logging
import json
from datetime import datetime
import magic
from pdfminer.high_level import extract_text as pdf_extract_text
from docx import Document
from werkzeug.utils import secure_filename
import os
from utils.ai_service import AIService

resume_analysis = Blueprint('resume_analysis', __name__)
logger = logging.getLogger(__name__)

def chunk_text(text, max_chunk_size=2000):
    """Split text into smaller chunks to avoid token limits"""
    text = text.replace('\x00', '')
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    chunks = []
    current_chunk = []
    current_size = 0

    for sentence in sentences:
        sentence_size = len(sentence) // 4 + 1

        if current_size + sentence_size > max_chunk_size:
            if current_chunk:
                chunks.append('. '.join(current_chunk) + '.')
            current_chunk = [sentence]
            current_size = sentence_size
        else:
            current_chunk.append(sentence)
            current_size += sentence_size

    if current_chunk:
        chunks.append('. '.join(current_chunk) + '.')

    return chunks

def analyze_chunk(chunk):
    """Analyze a single chunk of resume text using OpenAI"""
    try:
        logger.info("Starting chunk analysis")
        system_message = """You are an expert resume analyzer and script writer. Generate a concise video resume script and analysis with these sections:

        1. script: A well-structured video resume script (2-3 minutes) highlighting:
           - Professional introduction
           - Key achievements
           - Skills and expertise
           - Career goals

        2. key_points: Most important skills and experiences

        3. strengths: Main professional strengths

        4. improvements: Areas for growth

        5. talking_points: Key points to emphasize in the video

        Format the response as a JSON object with these exact keys. Each value should be an array of strings."""

        try:
            # Get OpenAI client instance through AIService
            ai_service = AIService.get_instance()
            client = ai_service.client
            logger.info("Retrieved OpenAI client for script generation")
        except Exception as client_error:
            logger.error(f"Error initializing OpenAI client: {str(client_error)}")
            return {'success': False, 'error': "AI service initialization failed"}

        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": f"Analyze this resume text and generate a script:\n\n{chunk}"}
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            logger.info("Successfully received OpenAI response")

            if not completion.choices:
                logger.error("OpenAI returned empty response")
                return {'success': False, 'error': "OpenAI returned empty response"}

            content = completion.choices[0].message.content
            if not content:
                logger.error("OpenAI response content is empty")
                return {'success': False, 'error': "OpenAI response content is empty"}

            try:
                analysis = json.loads(content)
                logger.info("Successfully parsed OpenAI response")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI response: {str(e)}\nResponse: {content}")
                return {'success': False, 'error': "Failed to parse AI response"}

            required_keys = ['script', 'key_points', 'strengths', 'improvements', 'talking_points']
            missing_keys = [key for key in required_keys if key not in analysis]
            if missing_keys:
                logger.error(f"Missing required fields in OpenAI response: {missing_keys}")
                return {'success': False, 'error': f"Missing required fields in response: {', '.join(missing_keys)}"}

            # Ensure all values are lists and convert script array to a single string
            for key in required_keys:
                if not isinstance(analysis[key], list):
                    analysis[key] = [analysis[key]] if analysis[key] else []
                if key == 'script':
                    # Join script array into a single string with proper formatting
                    analysis[key] = '\n\n'.join(analysis[key])

            logger.info("Successfully analyzed chunk")
            return {'success': True, 'analysis': analysis}

        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return {'success': False, 'error': f"AI analysis failed: {str(e)}"}

    except Exception as e:
        logger.error(f"Error analyzing chunk: {str(e)}")
        return {'success': False, 'error': str(e)}

def analyze_resume_with_openai(resume_text):
    """Analyze resume using OpenAI's GPT model"""
    try:
        resume_chunks = chunk_text(resume_text)
        all_analyses = []

        for chunk in resume_chunks:
            chunk_result = analyze_chunk(chunk)
            if not chunk_result['success']:
                return chunk_result
            all_analyses.append(chunk_result['analysis'])
            logger.info(f"Successfully analyzed chunk {len(all_analyses)}")

        if not all_analyses:
            return {
                'success': False,
                'error': 'Failed to analyze the resume. Please try again.'
            }

        merged_analysis = {
            'script': '',
            'key_points': [],
            'strengths': [],
            'improvements': [],
            'talking_points': []
        }

        # Merge all analyses
        for analysis in all_analyses:
            # Concatenate scripts with proper spacing
            if analysis.get('script'):
                merged_analysis['script'] += (analysis['script'] + '\n\n')

            # Merge other fields
            for key in ['key_points', 'strengths', 'improvements', 'talking_points']:
                merged_analysis[key].extend([
                    item for item in analysis.get(key, [])
                    if isinstance(item, str) and item.strip()
                ])

        # Clean up script
        merged_analysis['script'] = merged_analysis['script'].strip()

        # Remove duplicates while preserving order
        for key in ['key_points', 'strengths', 'improvements', 'talking_points']:
            merged_analysis[key] = list(dict.fromkeys([
                item for item in merged_analysis[key] if item.strip()
            ]))

        logger.info("Successfully merged all analyses")
        return {
            'success': True,
            'analysis': merged_analysis
        }

    except Exception as e:
        logger.error(f"Resume analysis error: {str(e)}")
        return {
            'success': False,
            'error': 'An error occurred during resume analysis. Please try again.'
        }

@resume_analysis.route('/resume/analyze', methods=['POST'])
@login_required
def analyze_resume():
    """Endpoint to analyze a resume and store the results"""
    try:
        if 'resume' not in request.files:
            return jsonify({'success': False, 'error': 'No resume file provided'}), 400

        file = request.files['resume']
        if not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        temp_path = os.path.join('/tmp', secure_filename(file.filename))
        try:
            file.save(temp_path)
            logger.info(f"Saved temporary file: {temp_path}")

            mime_type = magic.from_file(temp_path, mime=True)
            logger.info(f"Detected mime type: {mime_type}")

            if mime_type == 'application/pdf':
                resume_text = pdf_extract_text(temp_path)
            elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                doc = Document(temp_path)
                resume_text = '\n'.join([paragraph.text for paragraph in doc.paragraphs])
            elif mime_type.startswith('text/'):
                with open(temp_path, 'r', encoding='utf-8') as f:
                    resume_text = f.read()
            else:
                return jsonify({
                    'success': False,
                    'error': 'Unsupported file format. Please upload a PDF, DOC, DOCX, or TXT file.'
                }), 400

        except Exception as e:
            logger.error(f"Failed to process resume file: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Unable to process resume file. Please ensure it is not corrupted.'
            }), 400
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.info(f"Cleaned up temporary file: {temp_path}")
                except Exception as e:
                    logger.error(f"Failed to clean up temporary file: {str(e)}")

        resume_text = ' '.join(resume_text.split())
        resume_text = resume_text.replace('\x00', '')
        resume_text = ''.join(char for char in resume_text if ord(char) >= 32 or char == '\n')

        if len(resume_text) < 50:
            return jsonify({
                'success': False,
                'error': 'Resume content seems too short. Please upload a complete resume.'
            }), 400

        if len(resume_text) > 50000:
            return jsonify({
                'success': False,
                'error': 'Resume content is too long. Please upload a shorter resume.'
            }), 500

        logger.info(f"Successfully processed resume content of length {len(resume_text)}")

        analysis_result = analyze_resume_with_openai(resume_text)
        logger.info("Completed OpenAI analysis")

        if not analysis_result['success']:
            error_message = analysis_result.get('error', 'Unknown error occurred')
            logger.error(f"Analysis failed: {error_message}")
            return jsonify({
                'success': False,
                'error': error_message
            }), 500

        # Store analysis in database
        try:
            # Clean up the resume text and ensure proper data types
            cleaned_resume = resume_text[:5000].strip()

            # Format lists properly and ensure they're JSON serializable
            analysis_data = analysis_result.get('analysis', {})
            key_points = [str(point).strip() for point in analysis_data.get('key_points', []) if point][:10]
            strengths = [str(point).strip() for point in analysis_data.get('strengths', []) if point][:10]
            improvements = [str(point).strip() for point in analysis_data.get('improvements', []) if point][:10]
            talking_points = [str(point).strip() for point in analysis_data.get('talking_points', []) if point][:10]
            script = analysis_data.get('script', '')

            analysis = ResumeAnalysis(
                user_id=current_user.id,
                original_resume=cleaned_resume,
                key_points=key_points,
                strengths=strengths,
                improvements=improvements,
                talking_points=talking_points,
                script=script
            )

            db.session.add(analysis)
            db.session.flush()
            analysis_id = analysis.id

            db.session.commit()
            logger.info(f"Analysis stored successfully for user {current_user.id}")

            return jsonify({
                'success': True,
                'analysis': {
                    'key_points': key_points,
                    'strengths': strengths,
                    'improvements': improvements,
                    'talking_points': talking_points,
                    'script': script
                },
                'analysis_id': analysis_id
            })

        except Exception as e:
            logger.error(f"Database error while saving analysis: {str(e)}")
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': 'Failed to save analysis results. Please try again.'
            }), 500

    except Exception as e:
        logger.error(f"Unexpected error in analyze_resume: {str(e)}")
        if 'db.session' in locals():
            db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred while analyzing your resume'
        }), 500

@resume_analysis.route('/api/resume/analysis/<int:analysis_id>', methods=['GET'])
@login_required
def get_analysis(analysis_id):
    """Retrieve a specific resume analysis"""
    analysis = ResumeAnalysis.query.get_or_404(analysis_id)

    if analysis.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    return jsonify({
        'success': True,
        'analysis': {
            'key_points': analysis.key_points,
            'strengths': analysis.strengths,
            'improvements': analysis.improvements,
            'talking_points': analysis.talking_points,
            'script': analysis.script
        }
    })

@resume_analysis.route('/api/resume/latest-analysis', methods=['GET'])
@login_required
def get_latest_analysis():
    """Retrieve the most recent resume analysis for the current user"""
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id)\
        .order_by(ResumeAnalysis.created_at.desc())\
        .first()

    if not analysis:
        return jsonify({'error': 'No resume analysis found'}), 404

    return jsonify({
        'success': True,
        'analysis': {
            'key_points': analysis.key_points,
            'strengths': analysis.strengths,
            'improvements': analysis.improvements,
            'talking_points': analysis.talking_points,
            'script': analysis.script
        }
    })

@resume_analysis.route('/')
@login_required
def resume_analysis_page():
    """Render the resume analysis page"""
    return render_template('resume/analysis.html')