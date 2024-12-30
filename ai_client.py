import os
import logging
from openai import OpenAI, OpenAIError
from typing import Optional
from functools import wraps
from time import sleep

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global client instance and lock
_client_instance = None
_initialization_in_progress = False

def with_retry(max_retries=3, delay=1):
    """Decorator for retrying operations with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries == max_retries:
                        raise
                    logger.warning(f"Attempt {retries} failed: {str(e)}. Retrying...")
                    sleep(delay * (2 ** (retries - 1)))  # Exponential backoff
            return None
        return wrapper
    return decorator

@with_retry(max_retries=3)
def _verify_client(client: OpenAI) -> bool:
    """Verify the OpenAI client is working correctly"""
    try:
        client.models.list()
        return True
    except OpenAIError as e:
        logger.error(f"Failed to verify OpenAI client: {str(e)}")
        raise

def get_openai_client() -> Optional[OpenAI]:
    """
    Create and return an OpenAI client instance.
    Uses singleton pattern with proper error handling and verification.

    Returns:
        OpenAI: Configured OpenAI client instance

    Raises:
        ValueError: If API key is missing or initialization fails
    """
    global _client_instance, _initialization_in_progress

    # Return existing instance if available
    if _client_instance is not None:
        return _client_instance

    # Prevent concurrent initialization
    if _initialization_in_progress:
        logger.warning("Client initialization already in progress")
        return None

    try:
        _initialization_in_progress = True

        # Get API key from environment
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OpenAI API key not found in environment")
            raise ValueError("OpenAI API key not found in environment variables")

        # Initialize client with proper configuration
        logger.info("Initializing OpenAI client...")
        client = OpenAI(
            api_key=api_key,
            timeout=60.0,  # Increased timeout for stability
            max_retries=2  # Built-in retry mechanism
        )

        # Verify the client works
        if _verify_client(client):
            logger.info("Successfully verified OpenAI client connection")
            _client_instance = client
            return _client_instance

    except OpenAIError as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise ValueError(f"Failed to initialize AI service: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error during client initialization: {str(e)}")
        raise ValueError(f"Unable to initialize AI service: {str(e)}")

    finally:
        _initialization_in_progress = False

def cleanup_openai_client():
    """Cleanup the OpenAI client instance"""
    global _client_instance
    try:
        if _client_instance is not None:
            logger.info("Cleaning up OpenAI client...")
            _client_instance = None
    except Exception as e:
        logger.error(f"Error during OpenAI client cleanup: {str(e)}")