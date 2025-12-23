"""Vertex AI Gemini client wrapper."""

import os
import logging
from typing import Optional, List, Union
from pathlib import Path
import io

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel, Part
    from PIL import Image
except ImportError as e:
    raise ImportError(
        "vertexai package not installed. Install with: pip install google-cloud-aiplatform"
    ) from e

from app.config import (
    GCP_PROJECT_ID,
    GCP_LOCATION,
    GEMINI_MODEL,
)

logger = logging.getLogger(__name__)

# Global flag to track if Vertex AI is initialized
_vertex_initialized = False
_vertex_lock = None

def _get_lock():
    """Get a lock for thread-safe initialization."""
    global _vertex_lock
    if _vertex_lock is None:
        import threading
        _vertex_lock = threading.Lock()
    return _vertex_lock


def _ensure_vertex_initialized():
    """Ensure Vertex AI is initialized (thread-safe)."""
    global _vertex_initialized
    if not _vertex_initialized:
        lock = _get_lock()
        with lock:
            # Double-check after acquiring lock
            if not _vertex_initialized:
                if not GCP_PROJECT_ID:
                    raise ValueError("GCP_PROJECT_ID not found in environment variables")
                
                location = GCP_LOCATION or "global"
                try:
                    logger.info(f"Initializing Vertex AI: project={GCP_PROJECT_ID}, location={location}")
                    vertexai.init(project=GCP_PROJECT_ID, location=location)
                    _vertex_initialized = True
                    logger.info(f"Vertex AI initialized successfully: project={GCP_PROJECT_ID}, location={location}")
                except Exception as e:
                    error_msg = f"Failed to initialize Vertex AI: {type(e).__name__}: {e}"
                    if "credentials" in str(e).lower() or "authentication" in str(e).lower():
                        error_msg += "\n\nVertex AI requires Application Default Credentials (ADC)."
                        error_msg += "\nPlease run: gcloud auth application-default login"
                        error_msg += f"\nOr set GOOGLE_APPLICATION_CREDENTIALS environment variable to your service account key file."
                    logger.error(error_msg)
                    raise ValueError(error_msg) from e


def _convert_image_to_part(image: Union[Image.Image, Path, str, bytes]) -> Part:
    """
    Convert a PIL Image, file path, or bytes to Vertex AI Part.
    
    Args:
        image: PIL Image, Path to image file, or image bytes
        
    Returns:
        Part: Vertex AI Part object
    """
    if isinstance(image, Image.Image):
        # Convert PIL Image to PNG bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        return Part.from_data(data=image_bytes, mime_type="image/png")
    elif isinstance(image, (Path, str)):
        # Load from file path
        image_path = Path(image)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # Read bytes and determine mime type
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        
        # Determine mime type from extension
        ext = image_path.suffix.lower()
        mime_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_type_map.get(ext, "image/png")
        
        return Part.from_data(data=image_bytes, mime_type=mime_type)
    elif isinstance(image, bytes):
        # Already bytes, assume PNG
        return Part.from_data(data=image, mime_type="image/png")
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")


class VertexGeminiClient:
    """Wrapper for Vertex AI Gemini API calls."""
    
    def __init__(self, model_name: Optional[str] = None, location: Optional[str] = None):
        """
        Initialize Vertex Gemini client.
        
        Args:
            model_name: Model name (default: GEMINI_MODEL from config)
            location: GCP location (default: GCP_LOCATION from config or "global")
        """
        _ensure_vertex_initialized()
        self.model_name = model_name or GEMINI_MODEL
        self.location = location or GCP_LOCATION or "global"
        self._model = None
    
    def _get_model(self) -> GenerativeModel:
        """Get or create model instance."""
        if self._model is None:
            self._model = GenerativeModel(self.model_name)
        return self._model
    
    def generate_content(
        self,
        contents: Union[str, List[Union[str, Image.Image, Part]]],
        temperature: float = 0,
        max_output_tokens: int = 2048,
    ) -> str:
        """
        Generate content using Vertex AI Gemini.
        
        Args:
            contents: Prompt string, or list of prompts/images/Parts
            temperature: Generation temperature (default: 0)
            max_output_tokens: Maximum output tokens (default: 2048)
            
        Returns:
            str: Generated text response
        """
        model = self._get_model()
        
        # Convert contents to Vertex AI format
        if isinstance(contents, str):
            # Single prompt string
            vertex_contents = [contents]
        elif isinstance(contents, list):
            # List of prompts/images
            vertex_contents = []
            for item in contents:
                if isinstance(item, str):
                    vertex_contents.append(item)
                elif isinstance(item, Image.Image):
                    # Convert PIL Image to Part
                    vertex_contents.append(_convert_image_to_part(item))
                elif isinstance(item, Part):
                    vertex_contents.append(item)
                else:
                    raise TypeError(f"Unsupported content type: {type(item)}")
        else:
            raise TypeError(f"Unsupported contents type: {type(contents)}")
        
        # Generate content
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        
        response = model.generate_content(
            vertex_contents,
            generation_config=generation_config,
        )
        
        # Extract text from response
        # Handle different response formats (including reasoning models)
        if not response:
            raise ValueError("Empty response from Vertex AI Gemini")
        
        # Try to get text directly (this may raise ValueError if no text)
        try:
            if hasattr(response, 'text'):
                text = response.text
                if text:
                    return text.strip()
        except ValueError as e:
            # If accessing .text raises ValueError, check candidates directly
            pass
        
        # If no text from .text property, try to get from candidates
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            
            # Check finish_reason first
            finish_reason = getattr(candidate, 'finish_reason', None)
            if finish_reason == 'MAX_TOKENS':
                raise ValueError(f"Response hit max tokens limit ({max_output_tokens}). Consider increasing max_output_tokens. Note: Reasoning models may use tokens for internal reasoning.")
            elif finish_reason == 'SAFETY':
                raise ValueError("Response blocked by safety filters")
            
            # Try to extract text from candidate content parts
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    # Extract text from parts
                    text_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        return " ".join(text_parts).strip()
        
        raise ValueError("Empty response from Vertex AI Gemini - no text content found")


# Convenience function for backward compatibility
def generate_content(
    contents: Union[str, List[Union[str, Image.Image]]],
    model_name: Optional[str] = None,
    temperature: float = 0,
    max_output_tokens: int = 2048,
) -> str:
    """
    Generate content using Vertex AI Gemini (convenience function).
    
    Args:
        contents: Prompt string, or list of prompts/images
        model_name: Model name (default: GEMINI_MODEL from config)
        temperature: Generation temperature (default: 0)
        max_output_tokens: Maximum output tokens (default: 2048)
        
    Returns:
        str: Generated text response
    """
    client = VertexGeminiClient(model_name=model_name)
    return client.generate_content(
        contents=contents,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

