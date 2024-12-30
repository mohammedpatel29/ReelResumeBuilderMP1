from flask_wtf import FlaskForm
from wtforms import FileField
from wtforms.validators import DataRequired
import os
import io
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required, current_user
from models import VideoScript, ScriptSection, ResumeAnalysis, db
from werkzeug.utils import secure_filename
from datetime import datetime
import logging
import json
import re
from openai import OpenAI

script = Blueprint('script', __name__)
logger = logging.getLogger(__name__)

class ScriptGenerationForm(FlaskForm):
    resume = FileField('Resume', validators=[DataRequired()])

@script.route('/script/generate', methods=['GET', 'POST'])
@login_required
def generate_script():
    """Generate a video script from uploaded resume"""
    form = ScriptGenerationForm()
    logger.info("Accessing script generation page")

    if request.method == 'POST':
        logger.info("Starting script generation process")
        try:
            # Add detailed logging
            logger.info("Request method: POST")
            logger.info(f"Form data: {request.form}")
            logger.info(f"Files: {request.files}")

            if not form.validate_on_submit():
                logger.error("Form validation failed")
                return jsonify({'error': 'Invalid form submission'}), 400

            # Check if this is a regeneration request
            is_regeneration = request.form.get('regenerate', 'false') == 'true'
            resume_content = None
            analysis = None

            if is_regeneration:
                # For regeneration, get the latest resume analysis
                analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id)\
                    .order_by(ResumeAnalysis.created_at.desc())\
                    .first()

                if not analysis:
                    return jsonify({'error': 'No resume analysis found. Please upload a resume first.'}), 404

                resume_content = analysis.original_resume
                logger.info(f"Using existing resume analysis for regeneration (analysis_id: {analysis.id})")
            else:
                file = form.resume.data
                if not file:
                    logger.error("No resume file uploaded")
                    return jsonify({'error': 'Please upload a resume file'}), 400

                logger.info(f"Processing file: {file.filename}")

                # Extract and process text from file
                resume_content, error = extract_text_from_file(file)

                if error:
                    logger.error(f"File processing error: {error}")
                    return jsonify({'error': f"Could not process file: {error}"}), 400

                if not resume_content or len(resume_content.strip()) < 50:
                    logger.error("Insufficient content extracted from resume")
                    return jsonify({'error': 'Could not extract sufficient content from the resume'}), 400

                logger.info(f"Successfully extracted {len(resume_content)} characters from resume")

            if not resume_content or not resume_content.strip():
                return jsonify({'error': 'No readable content found in file'}), 400

            logger.info(f"Processing resume content (length: {len(resume_content)})")

            # Generate script using resume content and analysis
            script_sections, error = create_basic_script(resume_content, analysis)

            if error:
                logger.error(f"Script generation error: {error}")
                return jsonify({
                    'error': 'Script generation failed',
                    'details': error
                }), 500

            # Create video script record
            version_number = 1
            if is_regeneration:
                existing_count = VideoScript.query.filter_by(user_id=current_user.id).count()
                version_number = existing_count + 1

            video_script = VideoScript(
                user_id=current_user.id,
                title=f"Video Resume Script v{version_number} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                content=f"{'Regenerated' if is_regeneration else 'Generated'} from resume analysis"
            )
            db.session.add(video_script)
            db.session.flush()

            # Create script sections
            section_order = {
                'opening': 1,
                'background': 2,
                'experience': 3,
                'achievements': 4,
                'value_proposition': 5,
                'future_goals': 6,
                'closing': 7
            }

            for section_type, section_data in script_sections.items():
                section = ScriptSection(
                    script_id=video_script.id,
                    section_type=section_type,
                    content=section_data['content'],
                    order=section_order.get(section_type, 999)
                )
                db.session.add(section)

            db.session.commit()
            logger.info(f"Successfully saved script {video_script.id}")

            # Build the redirect URL using url_for
            try:
                redirect_url = url_for('video.list_videos')  
                response_data = {
                    'success': True,
                    'script_id': video_script.id,
                    'redirect_url': redirect_url,
                    'message': f'Script {"regenerated" if is_regeneration else "generated"} successfully'
                }

                return jsonify(response_data)
            except Exception as url_error:
                logger.error(f"URL generation error: {str(url_error)}")
                return jsonify({
                    'error': 'Script generated but redirect failed',
                    'details': str(url_error)
                }), 500

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error in script generation: {error_msg}")
            logger.exception("Full traceback:")
            db.session.rollback()
            return jsonify({
                'error': 'Script generation failed',
                'details': error_msg
            }), 500

    return render_template('script/generate.html', form=form)

def extract_text_from_file(file):
    """Extract text from various file formats"""
    try:
        filename = file.filename.lower()
        file_content = file.read()
        text = ""

        if filename.endswith('.txt'):
            import chardet
            detected = chardet.detect(file_content)
            text = file_content.decode(detected['encoding'] or 'utf-8', errors='replace')

        elif filename.endswith('.docx'):
            from docx import Document
            doc = Document(io.BytesIO(file_content))
            text = '\n'.join([paragraph.text for paragraph in doc.paragraphs])

        elif filename.endswith('.pdf'):
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                text = '\n'.join(page.extract_text() or '' for page in pdf.pages)

        else:
            return None, "Unsupported file format"

        text = ' '.join(text.split())
        text = ''.join(char for char in text if char.isprintable())

        return text, None

    except Exception as e:
        logger.error(f"Error extracting text: {str(e)}")
        return None, f"Error processing file: {str(e)}"

def create_basic_script(resume_content, analysis=None):
    """Create a comprehensive script template from resume content and analysis using OpenAI"""
    try:
        # Default script sections (used as fallback)
        default_sections = {
            "opening": {
                "timing": "[0:00-0:15]",
                "content": "Hello, I am excited to share my professional journey with you. In the next few minutes, I will walk you through my experience and what I can bring to your organization."
            },
            "background": {
                "timing": "[0:15-0:45]",
                "content": "My professional background includes diverse experience in my field, where I have consistently focused on growth and impact."
            },
            "experience": {
                "timing": "[0:45-1:30]",
                "content": "Throughout my career, I have developed expertise in several key areas, including project management, team collaboration, and innovative problem-solving."
            },
            "achievements": {
                "timing": "[1:30-2:00]",
                "content": "I have achieved significant results through dedication and strategic thinking."
            },
            "value_proposition": {
                "timing": "[2:00-2:30]",
                "content": "What sets me apart is my combination of technical expertise and strong interpersonal skills."
            },
            "future_goals": {
                "timing": "[2:30-2:45]",
                "content": "Looking ahead, I am excited about opportunities to contribute to innovative projects and continue growing professionally."
            },
            "closing": {
                "timing": "[2:45-3:00]",
                "content": "Thank you for watching my video resume. I look forward to discussing how my experience can benefit your team."
            }
        }

        try:
            from utils.ai_client import get_openai_client

            # Get OpenAI client instance
            client = get_openai_client()
            logger.info("Retrieved OpenAI client for script generation")

            # Prepare context for OpenAI based on analysis data
            context = ""
            if analysis:
                context = "\n".join([
                    "Key Skills & Experience:",
                    "\n".join(f"- {point}" for point in analysis.key_points) if analysis.key_points else "N/A",
                    "\nProfessional Strengths:",
                    "\n".join(f"- {strength}" for strength in analysis.strengths) if analysis.strengths else "N/A",
                    "\nKey Talking Points:",
                    "\n".join(f"- {point}" for point in analysis.talking_points) if analysis.talking_points else "N/A"
                ])

            # Enhanced system message for more detailed output
            system_message = """You are an expert video resume scriptwriter specializing in creating compelling, detailed scripts that showcase professional achievements and potential. Your goal is to create a script that is both engaging and rich in specific details from the candidate's resume.

Key Requirements:
1. Use actual metrics, achievements, and project details from the resume
2. Maintain a conversational yet professional tone
3. Include specific examples that demonstrate skills
4. Reference actual technologies, tools, and methodologies used
5. Incorporate quantifiable achievements and results
6. Create smooth transitions between sections
7. Use the candidate's own terminology and industry language

Structure each section with specific timing and detailed content:
1. Opening [0:00-0:15]: Engaging introduction with professional identity and key expertise areas
2. Background [0:15-0:45]: Detailed professional journey highlighting key roles and responsibilities
3. Experience [0:45-1:30]: In-depth discussion of 2-3 significant projects with specific impacts
4. Achievements [1:30-2:00]: Quantifiable results and recognition with specific metrics
5. Value Proposition [2:00-2:30]: Unique combination of skills and experiences with examples
6. Future Goals [2:30-2:45]: Career aspirations aligned with industry trends
7. Closing [2:45-3:00]: Strong call to action emphasizing mutual benefit

Format: Structure each section with its timing marker followed by detailed, engaging content that directly references the candidate's experience."""

            # Enhanced user message for more specific content
            user_message = f"""Resume Content:\n{resume_content}\n\nAnalysis Data:\n{context}

Create a highly detailed, personalized video resume script that:
1. Uses specific numbers and metrics from the resume (e.g., "Increased team productivity by 45%" rather than "Improved productivity")
2. Names actual projects, technologies, and tools used
3. Includes specific industries and company types worked with
4. References actual job titles and roles held
5. Mentions specific certifications, awards, or recognition received
6. Incorporates actual methodologies and processes used
7. Uses specific examples of problems solved and solutions implemented

Important:
- Include real numbers and percentages from their experience
- Name specific technologies and tools they've used
- Reference actual projects they've worked on
- Use their industry-specific terminology
- Include specific achievements with measurable results"""

            # Generate script using OpenAI with increased tokens and adjusted parameters
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.7,
                    max_tokens=2000,  # Increased for more detailed content
                    presence_penalty=0.6,
                    frequency_penalty=0.3
                )

                if not response.choices:
                    raise ValueError("OpenAI returned empty response")

                # Extract the generated content
                script_content = response.choices[0].message.content

                if not script_content:
                    raise ValueError("OpenAI response content is empty")
            except Exception as api_error:
                logger.error(f"OpenAI API error: {str(api_error)}")
                raise ValueError(f"Failed to generate script: {str(api_error)}")

            # Parse the response into sections
            sections = {}
            current_section = None
            current_content = []

            for line in script_content.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # Check for section headers
                section_match = re.search(r'^(Opening|Background|Experience|Achievements|Value Proposition|Future Goals|Closing)\s*\[([^\]]+)\]', line, re.IGNORECASE)

                if section_match:
                    # Save previous section
                    if current_section:
                        sections[current_section] = {
                            "timing": timing,
                            "content": '\n'.join(current_content).strip()
                        }

                    # Start new section
                    current_section = section_match.group(1).lower().replace(' ', '_')
                    timing = section_match.group(2)
                    current_content = []
                else:
                    current_content.append(line)

            # Add the last section
            if current_section and current_content:
                sections[current_section] = {
                    "timing": timing,
                    "content": '\n'.join(current_content).strip()
                }

            # Ensure all required sections are present
            for section_name, default_section in default_sections.items():
                if section_name not in sections or not sections[section_name].get('content', '').strip():
                    sections[section_name] = default_section

            return sections, None
        except Exception as api_error:
            logger.error(f"OpenAI API error: {str(api_error)}")
            return default_sections, None

    except Exception as e:
        logger.error(f"Script creation error: {str(e)}")
        return None, f"Error creating script: {str(e)}"

@script.route('/scripts')
@login_required
def list_scripts():
    try:
        scripts = VideoScript.query.filter_by(user_id=current_user.id)\
            .order_by(VideoScript.created_at.desc())\
            .all()
        return render_template('script/list.html', scripts=scripts)
    except Exception as e:
        logger.error(f"Error listing scripts: {str(e)}")
        return render_template('errors/500.html'), 500

@script.route('/script/<int:script_id>')
@login_required
def view_script(script_id):
    try:
        script = VideoScript.query.get(script_id)
        if not script:
            logger.error(f"Script not found: {script_id}")
            return render_template('errors/404.html'), 404
        if script.user_id != current_user.id:
            logger.warning(f"Unauthorized access attempt to script {script_id} by user {current_user.id}")
            return render_template('errors/403.html'), 403

        # Get the latest resume analysis
        analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id)\
            .order_by(ResumeAnalysis.created_at.desc())\
            .first()

        return render_template('script/view.html', 
                             script=script, 
                             analysis=analysis)
    except Exception as e:
        logger.error(f"Error viewing script: {str(e)}")
        return render_template('errors/500.html'), 500

@script.route('/script/<int:script_id>/teleprompter')
@login_required
def teleprompter(script_id):
    try:
        script = VideoScript.query.get_or_404(script_id)
        if script.user_id != current_user.id:
            return render_template('errors/403.html'), 403

        sections = ScriptSection.query.filter_by(script_id=script_id)\
            .order_by(ScriptSection.order).all()

        return render_template('script/teleprompter.html', 
                             script=script, 
                             sections=sections)
    except Exception as e:
        logger.error(f"Error in teleprompter view: {str(e)}")
        return render_template('errors/500.html'), 500

@script.route('/api/script/<int:script_id>/content')
@login_required
def get_script_content(script_id):
    try:
        script = VideoScript.query.get_or_404(script_id)
        if script.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        sections = ScriptSection.query.filter_by(script_id=script_id)\
            .order_by(ScriptSection.order).all()

        formatted_content = []
        for section in sections:
            formatted_content.append(f"<h3>{section.section_type.title()}</h3>")
            formatted_content.append(f"<p>{section.content}</p>")

        return jsonify({
            'success': True,
            'content': '\n'.join(formatted_content)
        })
    except Exception as e:
        logger.error(f"Error getting script content: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@script.route('/script/<int:script_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_script(script_id):
    try:
        script = VideoScript.query.get_or_404(script_id)
        if script.user_id != current_user.id:
            flash('Access denied. This script does not belong to you.', 'danger')
            return redirect(url_for('script.list_scripts'))

        sections = ScriptSection.query.filter_by(script_id=script_id)\
            .order_by(ScriptSection.order).all()

        return render_template('script/edit.html', 
                             script=script, 
                             sections=sections)

    except Exception as e:
        logger.error(f"Error editing script: {str(e)}")
        return render_template('errors/500.html'), 500