import os
import logging
from functools import wraps
from time import sleep
from openai import OpenAI, OpenAIError, APIError, RateLimitError, APIConnectionError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIServiceError(Exception):
    """Custom exception for AI service errors"""
    pass

def retry_on_error(max_retries=3, base_delay=1):
    """Decorator for retrying operations with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (APIError, RateLimitError, APIConnectionError) as e:
                    last_error = e
                    if isinstance(e, RateLimitError):
                        logger.warning(f"Rate limit hit, waiting longer before retry")
                        delay = base_delay * (4 ** attempt)  # Longer delay for rate limits
                    else:
                        delay = base_delay * (2 ** attempt)
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay}s...")
                    sleep(delay)
                except Exception as e:
                    logger.error(f"Unexpected error: {str(e)}")
                    raise AIServiceError(f"Unexpected error: {str(e)}")

            logger.error(f"All {max_retries} attempts failed. Last error: {str(last_error)}")
            raise AIServiceError(f"Operation failed after {max_retries} attempts: {str(last_error)}")
        return wrapper
    return decorator

class AIService:
    _instance = None
    _client = None
    _initialization_lock = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIService, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls):
        """Get singleton instance with lazy initialization"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @retry_on_error(max_retries=3)
    def _initialize_client(self):
        """Initialize OpenAI client with retries"""
        if self._client is not None:
            return

        if self._initialization_lock:
            logger.warning("Client initialization already in progress")
            return

        try:
            self._initialization_lock = True
            api_key = os.getenv('OPENAI_API_KEY')

            if not api_key:
                raise AIServiceError("OpenAI API key not found in environment variables")

            self._client = OpenAI(
                api_key=api_key,
                timeout=60.0,
                max_retries=2
            )

            # Test API connection with a lightweight call
            try:
                self._client.models.list()
                logger.info("AI service initialized successfully")
            except Exception as e:
                logger.error(f"API test call failed: {str(e)}")
                self._client = None
                raise AIServiceError(f"API test call failed: {str(e)}")

        except OpenAIError as e:
            logger.error(f"OpenAI API error during initialization: {str(e)}")
            self._client = None
            raise AIServiceError(f"Failed to initialize AI service: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during initialization: {str(e)}")
            self._client = None
            raise AIServiceError(f"Unable to initialize AI service: {str(e)}")
        finally:
            self._initialization_lock = False

    @property
    def client(self):
        """Get initialized OpenAI client with retry logic"""
        if self._client is None:
            self._initialize_client()
        return self._client

    def cleanup(self):
        """Cleanup AI service resources"""
        try:
            self._client = None
            logger.info("AI service cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during AI service cleanup: {str(e)}")

    @retry_on_error(max_retries=2)
    def analyze_resume(self, resume_text):
        """Analyze resume text with retries"""
        if not resume_text or not isinstance(resume_text, str):
            raise ValueError("Invalid resume text provided")

        try:
            if not self.client:
                raise AIServiceError("AI service not properly initialized")

            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional resume analyzer."},
                    {"role": "user", "content": f"Please analyze this resume:\n\n{resume_text}"}
                ],
                temperature=0.7,
                max_tokens=1000
            )

            if not response or not response.choices:
                raise AIServiceError("Empty response from AI service")

            return response.choices[0].message.content

        except OpenAIError as e:
            logger.error(f"OpenAI API error during resume analysis: {str(e)}")
            raise AIServiceError(f"Failed to analyze resume: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during resume analysis: {str(e)}")
            raise AIServiceError(f"Failed to analyze resume: {str(e)}")

    @retry_on_error(max_retries=2)
    def generate_script(self, prompt):
        """Generate video script with retries"""
        if not prompt or not isinstance(prompt, str):
            raise ValueError("Invalid prompt provided")

        try:
            if not self.client:
                raise AIServiceError("AI service not properly initialized")

            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional video script writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=1500
            )

            if not response or not response.choices:
                raise AIServiceError("Empty response from AI service")

            return response.choices[0].message.content

        except OpenAIError as e:
            logger.error(f"OpenAI API error during script generation: {str(e)}")
            raise AIServiceError(f"Failed to generate script: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during script generation: {str(e)}")
            raise AIServiceError(f"Failed to generate script: {str(e)}")