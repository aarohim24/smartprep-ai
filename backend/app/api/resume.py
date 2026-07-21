"""
SmartPrep AI - Resume Upload API
POST /api/v1/upload-resume
"""
import asyncio
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.schemas import ResumeUploadResponse
from app.services.resume_parser import resume_parser
from app.services.rag_service import rag_service
from app.services.llm_service import llm_service
from app.services.session_store import session_store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".text", ".md"}


@router.post("/upload-resume", response_model=ResumeUploadResponse)
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload and process a resume (PDF or TXT).
    - Validates file type and size (post-read, not header-trusting)
    - Extracts text
    - Chunks and embeds into FAISS vector store
    - Returns session_id for subsequent API calls
    """
    # Validate filename safely
    filename = file.filename or "upload"
    file_ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Unsupported file type. Allowed: PDF, TXT, MD")

    # Read and validate actual size (not Content-Length header)
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Empty file uploaded")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Max size: 10MB (got {len(file_bytes) // 1024}KB)")

    # Extract text
    try:
        extracted_text = resume_parser.extract_text(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Resume parsing error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to parse resume. Please check the file is not corrupted.")

    if len(extracted_text) < 100:
        raise HTTPException(422, "Resume text too short. Please upload a valid resume.")

    session_id = str(uuid.uuid4())

    # Run RAG indexing and skill extraction in parallel — they are independent.
    async def _extract_skills_safe():
        try:
            return await llm_service.extract_skills(extracted_text)
        except Exception as e:
            logger.warning(f"Skill extraction failed (non-fatal): {e}")
            return []

    try:
        chunk_count, skills = await asyncio.gather(
            rag_service.index_document(session_id, extracted_text, "resume"),
            _extract_skills_safe(),
        )
    except Exception as e:
        logger.error(f"RAG indexing error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to index resume. Please try again.")

    # Persist session (async-safe)
    await session_store.create(session_id, {
        "resume_text": extracted_text,
        "skills": skills,
        "filename": filename,
    })

    logger.info(f"Resume processed: session={session_id}, chunks={chunk_count}, skills={len(skills)}")

    preview = extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
    return ResumeUploadResponse(
        session_id=session_id,
        extracted_text=preview,
        chunk_count=chunk_count,
        skills_detected=skills,
    )
