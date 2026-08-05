from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.dependencies import get_knowledge_document_service
from app.schemas.knowledge import KnowledgeDocumentResponse
from app.services.knowledge import (
    KnowledgeDocumentAlreadyExistsError,
    KnowledgeDocumentDeletionError,
    KnowledgeDocumentIndexingError,
    KnowledgeDocumentService,
)
from app.services.storage import DocumentStorageError

router = APIRouter(
    prefix="/documents",
    tags=["private-knowledge"],
)


@router.post(
    "",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    service: Annotated[
        KnowledgeDocumentService,
        Depends(get_knowledge_document_service),
    ],
    uploaded_by_user_id: Annotated[
        UUID | None,
        Header(alias="X-User-ID"),
    ] = None,
) -> KnowledgeDocumentResponse:
    """Validate, store, index, and return one tenant-owned document."""

    filename = (file.filename or "").strip()
    declared_media_type = file.content_type

    try:
        raw_content = await file.read(service.max_upload_bytes + 1)
    finally:
        await file.close()

    if len(raw_content) > service.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Document exceeds the maximum allowed size.",
        )

    try:
        return await service.upload(
            tenant_id=tenant_id,
            uploaded_by_user_id=uploaded_by_user_id,
            filename=filename,
            declared_media_type=declared_media_type,
            raw_content=raw_content,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except KnowledgeDocumentAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except KnowledgeDocumentIndexingError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Private document storage is temporarily unavailable.",
        ) from error


@router.get("", response_model=list[KnowledgeDocumentResponse])
async def list_documents(
    tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    service: Annotated[
        KnowledgeDocumentService,
        Depends(get_knowledge_document_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[KnowledgeDocumentResponse]:
    """List recent private documents only within the tenant boundary."""

    return await service.list(
        tenant_id=tenant_id,
        limit=limit,
    )


@router.get("/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_document(
    document_id: UUID,
    tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    service: Annotated[
        KnowledgeDocumentService,
        Depends(get_knowledge_document_service),
    ],
) -> KnowledgeDocumentResponse:
    """Return one private document only within the tenant boundary."""

    document = await service.get(
        tenant_id=tenant_id,
        document_id=document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Private document was not found.",
        )

    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    service: Annotated[
        KnowledgeDocumentService,
        Depends(get_knowledge_document_service),
    ],
) -> Response:
    """Delete one tenant document and its external artifacts."""

    try:
        deleted = await service.delete(
            tenant_id=tenant_id,
            document_id=document_id,
        )
    except KnowledgeDocumentDeletionError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Private document was not found.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
