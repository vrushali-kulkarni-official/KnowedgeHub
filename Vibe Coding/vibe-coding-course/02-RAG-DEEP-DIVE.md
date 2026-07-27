# Part 8: RAG — The Pattern That Powers Every AI SaaS

> **Continue from:** `01-LANGCHAIN-FUNDAMENTALS.md`
>
> **In this part:** you learn RAG (Retrieval Augmented Generation) from the ground up. By the end, you'll be able to build "chat with your docs" features that actually work.

---

## 8.1 What is RAG and Why It's the #1 Pattern

**RAG = Retrieval Augmented Generation.**

It's the pattern where:
1. User asks a question
2. You search a knowledge base for relevant info
3. You give that info to the LLM along with the question
4. LLM answers using the retrieved info

**Why it's the #1 pattern:**
- LLMs don't know your private data (they were trained before it existed)
- LLMs hallucinate (they make stuff up)
- RAG fixes both: it gives the LLM the right info, and the LLM can cite it

This is how every "AI search" product works. Notion AI, Slack AI, the "chat with your PDF" features, customer support bots — all RAG under the hood.

## 8.2 The RAG Pipeline (Step by Step)

```
┌─────────────────────────────────────────────────────────────────┐
│                        INDEXING (one-time / per-doc)            │
│                                                                 │
│  PDF/Doc → Load → Split → Embed → Store in Vector DB           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        QUERYING (per-question)                  │
│                                                                 │
│  Question → Embed → Search Vector DB → Top K chunks             │
│                                                                 │
│  Question + chunks → Prompt → LLM → Answer                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

The two phases are different:
- **Indexing** is slow, runs in the background, doesn't need to be instant
- **Querying** is real-time, must be fast (< 2 seconds ideally)

## 8.3 The Document Models (the data layer for RAG)

```python
# app/db/models/document.py
"""
The Document model — represents an uploaded PDF (or other file).

Each document belongs to a user (multi-tenant).
Each document gets processed: split into chunks, embedded, stored in vector DB.
"""

import uuid
from datetime import datetime
from enum import Enum  # For the status enum

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentStatus(str, Enum):
    """
    The processing status of a document.

    States:
    - PENDING: just uploaded, not yet processed
    - PROCESSING: chunks being created and embedded
    - READY: ready to be queried
    - FAILED: something went wrong (we store the error)
    """
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    """An uploaded document."""
    __tablename__ = "documents"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign key to the user who owns this document
    # `ondelete="CASCADE"` means if the user is deleted, their docs are too
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,  # Fast lookup of "give me all docs for user X"
        nullable=False,
    )

    # File metadata
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)

    # Processing metadata
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,  # Fast lookup of "give me all processing docs"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    # Relationship to the user (so we can do `document.user.email`)
    # We don't load it by default — `.lazy="select"` means it's loaded on access
    # user = relationship("User", back_populates="documents")
```

And the chat models:

```python
# app/db/models/chat_session.py
"""A chat session — a conversation about one or more documents."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChatSession(Base):
    """A chat session tied to a user and (optionally) specific documents."""
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), default="New Chat", nullable=False)
    # The document IDs this chat is about. Empty list = all user's docs.
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    # Relationship: a session has many messages
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",  # Delete messages when session is deleted
        order_by="Message.created_at",  # Always ordered by time
    )


# app/db/models/message.py
"""A single message in a chat session."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MessageRole(str, Enum):
    """Who said this message."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"  # for context messages


class Message(Base):
    """A single message in a chat session."""
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole, name="message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional: which documents were used to answer this
    sources: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    # Token usage tracking
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # LLM model used (so you can A/B test or migrate)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relationship back to the session
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
```

## 8.4 The Vector Store Layer (ChromaDB)

```python
# app/services/llm/vector_store.py
"""
The vector store — where embeddings live.

We use ChromaDB because:
- Free, open source
- Runs locally (no external service needed)
- Embedded mode (no separate server to manage)
- Good enough for 99% of use cases
- Easy to migrate to pgvector or Pinecone later

Alternatives:
- pgvector: PostgreSQL extension, scales with your DB
- Qdrant: faster, more features, but needs separate server
- Weaviate: similar to Qdrant
- FAISS: meta's library, low-level, you build the rest
- Pinecone: hosted, paid, very easy
"""

import shutil
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
# In production, swap with: from langchain_openai import OpenAIEmbeddings
# Or: from langchain_huggingface import HuggingFaceEmbeddings  (free, local)

from app.config import settings


@lru_cache
def get_embeddings():
    """
    Returns the embeddings model.

    The embeddings model converts text → vector (a list of floats).
    The vector represents the meaning of the text, so similar texts
    have similar vectors.

    Google text-embedding-004: 768 dimensions, fast, free tier.
    OpenAI text-embedding-3-small: 1536 dimensions, paid, high quality.
    HuggingFace all-MiniLM-L6-v2: 384 dimensions, free, runs locally.
    """
    if settings.llm_provider == "google":
        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=settings.llm_api_key,
        )
    # Add other providers as needed
    raise ValueError(f"No embeddings configured for {settings.llm_provider}")


@lru_cache
def get_vector_store() -> Chroma:
    """
    Returns the ChromaDB vector store.

    Chroma is configured in "persistent" mode — it saves to disk,
    so data survives restarts.

    The collection name is set in settings; one collection per app.
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    # Persistent client — saves to disk
    client = chromadb.PersistentClient(
        path=settings.vector_store_path,
        settings=ChromaSettings(anonymized_telemetry=False),  # Don't phone home
    )

    # Get or create the collection
    collection = client.get_or_create_collection(
        name=settings.vector_store_collection,
        # cosine similarity is the standard for text embeddings
        metadata={"hnsw:space": "cosine"},
    )

    # Wrap in LangChain's interface
    return Chroma(
        client=client,
        collection_name=settings.vector_store_collection,
        embedding_function=get_embeddings(),
    )


def add_document_chunks(
    user_id: str,
    document_id: str,
    chunks: list[str],
    metadata: list[dict] | None = None,
) -> list[str]:
    """
    Add document chunks to the vector store.

    Args:
        user_id: Who owns this document (used for filtering)
        document_id: The document ID
        chunks: The text chunks (already split)
        metadata: Optional metadata for each chunk (filename, page, etc.)

    Returns:
        The list of chunk IDs
    """
    vector_store = get_vector_store()

    # Generate IDs (Chroma needs unique string IDs)
    chunk_ids = [f"{document_id}_{i}" for i in range(len(chunks))]

    # Merge user_id and document_id into metadata for filtering
    if metadata is None:
        metadata = [{}] * len(chunks)
    for m in metadata:
        m["user_id"] = user_id
        m["document_id"] = document_id

    # Add to the store. LangChain handles the embedding.
    vector_store.add_texts(
        texts=chunks,
        metadatas=metadata,
        ids=chunk_ids,
    )

    return chunk_ids


def search_user_documents(
    user_id: str,
    query: str,
    k: int = 5,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """
    Search the user's documents for chunks relevant to the query.

    Args:
        user_id: Whose documents to search (CRITICAL for multi-tenant)
        query: The user's question
        k: How many chunks to return
        document_ids: Optional — restrict to specific documents

    Returns:
        A list of dicts with 'content', 'metadata', and 'score'
    """
    vector_store = get_vector_store()

    # Build a filter. This is the security boundary —
    # users can ONLY search their own documents.
    filter_dict = {"user_id": user_id}
    if document_ids:
        # Chroma uses $in for "in this list"
        filter_dict["document_id"] = {"$in": document_ids}

    # Similarity search with scores
    # Lower score = more similar (for cosine distance)
    results = vector_store.similarity_search_with_score(
        query=query,
        k=k,
        filter=filter_dict,
    )

    # Format the results
    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": score,  # lower is better
        }
        for doc, score in results
    ]


def delete_document_chunks(document_id: str) -> None:
    """Delete all chunks for a document (when the doc is deleted)."""
    vector_store = get_vector_store()
    vector_store.delete(filter={"document_id": document_id})
```

**The CRITICAL line:** `filter_dict = {"user_id": user_id}`. This is what makes the SaaS multi-tenant. **Never** let a user query without this filter. It's a security boundary.

## 8.5 The Document Processor (load → split → embed)

```python
# app/workers/pdf_processor.py
"""
The PDF processor — runs in the background after a user uploads a file.

Steps:
1. Load the PDF
2. Split it into chunks
3. Embed the chunks
4. Store in the vector store
5. Update the document status
"""

import uuid

from pypdf import PdfReader  # Pure-Python PDF reader, free
# Alternatives: pdfplumber (more features), pymupdf (fastest)

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.db.models.document import Document, DocumentStatus
from app.services.llm.vector_store import add_document_chunks


def extract_text_from_pdf(file_path: str) -> list[dict]:
    """
    Extract text from a PDF.

    Returns a list of {text, page_number} dicts.
    Keeping page numbers lets us cite them in the response.
    """
    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text.strip():  # Skip empty pages
            pages.append({
                "text": text,
                "page_number": i + 1,  # 1-indexed for human display
            })
    return pages


def split_pages_into_chunks(pages: list[dict], chunk_size: int = 1000, chunk_overlap: int = 200) -> list[dict]:
    """
    Split pages into chunks.

    Why we chunk:
    - LLMs have a context limit (e.g. 1M tokens for Gemini, but still)
    - Smaller chunks = more focused retrieval
    - The right size depends on your content

    chunk_size: max characters per chunk
    chunk_overlap: how many chars to repeat between chunks (preserves context)

    Why RecursiveCharacterTextSplitter:
    - Tries to split on paragraphs first
    - Then sentences
    - Then words
    - Preserves meaning better than naive char splits
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # These are the separators it tries, in order
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for page in pages:
        page_chunks = splitter.split_text(page["text"])
        for chunk in page_chunks:
            chunks.append({
                "text": chunk,
                "page_number": page["page_number"],
            })
    return chunks


async def process_document(document: Document) -> None:
    """
    Process a document: extract, split, embed, store.

    This is the "indexing" phase of RAG.
    Called by the background worker after upload.
    """
    try:
        # 1. Update status to PROCESSING
        document.status = DocumentStatus.PROCESSING
        await document.save()  # pseudo-code, use your session

        # 2. Extract text from PDF
        pages = extract_text_from_pdf(document.file_path)

        # 3. Split into chunks
        chunks = split_pages_into_chunks(pages)

        # 4. Embed and store
        texts = [c["text"] for c in chunks]
        metadata = [
            {
                "page_number": c["page_number"],
                "filename": document.filename,
            }
            for c in chunks
        ]
        chunk_ids = add_document_chunks(
            user_id=str(document.user_id),
            document_id=str(document.id),
            chunks=texts,
            metadata=metadata,
        )

        # 5. Update the document
        document.status = DocumentStatus.READY
        document.chunk_count = len(chunks)
        await document.save()

    except Exception as e:
        document.status = DocumentStatus.FAILED
        document.error_message = str(e)
        await document.save()
        raise
```

## 8.6 The Chat Service (the actual RAG query)

This is where everything comes together. The user asks a question, we search, we ask the LLM, we return the answer.

```python
# app/services/chat_service.py
"""
The chat service — the brain of DocuMind AI.

Flow:
1. User asks a question
2. We search the user's documents for relevant chunks
3. We build a prompt with: system message + context + history + question
4. We call the LLM
5. We save the user message and the AI response
6. We return the answer
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload  # For loading relationships

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.db.models.chat_session import ChatSession
from app.db.models.message import Message, MessageRole
from app.services.llm.chains import get_chat_chain
from app.services.llm.vector_store import search_user_documents


async def get_or_create_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID | None = None
) -> ChatSession:
    """Get an existing chat session or create a new one."""
    if session_id:
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .options(selectinload(ChatSession.messages))
        )
        session = result.scalar_one_or_none()
        if session:
            return session
        # Session not found or not owned by user — create a new one

    # Create a new session
    session = ChatSession(user_id=user_id)
    db.add(session)
    await db.commit()
    await db.refresh(session, attribute_names=["messages"])
    return session


async def get_chat_history(db: AsyncSession, session_id: uuid.UUID, max_messages: int = 10) -> list[dict]:
    """
    Get the recent chat history for a session.

    We use a sliding window (max_messages) because:
    - Sending 100 messages to the LLM is expensive
    - Old messages are usually less relevant
    - 10 messages is a good default
    """
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(max_messages)
    )
    messages = result.scalars().all()
    # Reverse to chronological order (oldest first)
    return [
        {"role": msg.role.value, "content": msg.content}
        for msg in reversed(messages)
    ]


async def send_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    message: str,
) -> dict:
    """
    Send a message and get an AI response.

    This is the main entry point for the chat feature.
    """
    # 1. Get the session (verifies ownership)
    session = await get_or_create_session(db, user_id, session_id)

    # 2. Get chat history
    history = await get_chat_history(db, session.id)

    # 3. Search the user's documents
    # This is the RAG part: find relevant chunks to include as context
    relevant_chunks = search_user_documents(
        user_id=str(user_id),
        query=message,
        k=5,  # top 5 most relevant chunks
        document_ids=[str(d) for d in session.document_ids] if session.document_ids else None,
    )

    # 4. Build the context from the chunks
    context = "\n\n---\n\n".join([
        f"[From {chunk['metadata'].get('filename', 'unknown')}, "
        f"page {chunk['metadata'].get('page_number', '?')}]\n{chunk['content']}"
        for chunk in relevant_chunks
    ])

    # 5. Build the messages for the LLM
    messages = [
        SystemMessage(content=(
            "You are DocuMind AI, a helpful assistant that answers questions "
            "based on the user's documents. Use the provided context to answer. "
            "If the context doesn't contain the answer, say so honestly. "
            "Cite the source (filename and page) when you use information from the context."
        )),
    ]

    # Add the chat history
    for h in history:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        elif h["role"] == "assistant":
            messages.append(AIMessage(content=h["content"]))

    # Add the current context and question
    messages.append(HumanMessage(content=f"Context:\n{context}\n\nQuestion: {message}"))

    # 6. Call the LLM
    from app.services.llm.llm_factory import get_llm
    llm = get_llm()
    response = await llm.ainvoke(messages)

    # 7. Save both messages
    user_msg = Message(
        session_id=session.id,
        role=MessageRole.USER,
        content=message,
    )
    assistant_msg = Message(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=response.content,
        sources=[
            {
                "document_id": chunk["metadata"].get("document_id"),
                "filename": chunk["metadata"].get("filename"),
                "page": chunk["metadata"].get("page_number"),
                "score": chunk["score"],
            }
            for chunk in relevant_chunks
        ],
        prompt_tokens=response.usage_metadata.get("input_tokens") if response.usage_metadata else None,
        completion_tokens=response.usage_metadata.get("output_tokens") if response.usage_metadata else None,
        model=response.response_metadata.get("model_name") if response.response_metadata else None,
    )
    db.add_all([user_msg, assistant_msg])
    await db.commit()

    # 8. Return
    return {
        "session_id": str(session.id),
        "message": response.content,
        "sources": assistant_msg.sources,
    }
```

## 8.7 The Chat Endpoint (the API layer)

```python
# app/api/v1/chat.py
"""
The chat API endpoints.

This is the thin layer the user actually talks to.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Send a message and get an AI response.

    This uses RAG: the AI will only answer based on the user's documents.
    """
    result = await chat_service.send_message(
        db=db,
        user_id=current_user.id,
        session_id=request.session_id,
        message=request.message,
    )
    return ChatResponse(**result)


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the message history for a chat session."""
    from sqlalchemy import select
    from app.db.models.chat_session import ChatSession
    from app.db.models.message import Message

    # Verify the session belongs to the user
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "role": m.role.value,
            "content": m.content,
            "sources": m.sources,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
```

## 8.8 The Document Upload Endpoint

```python
# app/api/v1/documents.py
"""
The documents API: upload, list, delete.
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.db.models.document import Document, DocumentStatus
from app.db.models.user import User
from app.schemas.document import DocumentResponse
from app.workers.pdf_processor import process_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Upload a PDF document.

    The file is saved to disk, a Document record is created with status PENDING,
    and a background task is queued to process it.
    """
    # 1. Validate the file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext} not allowed. Allowed: {settings.allowed_extensions}",
        )

    # 2. Read and check size
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large")

    # 3. Save to disk
    # user_id/doc_id/filename structure for easy cleanup
    user_dir = os.path.join(settings.upload_dir, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)

    doc_id = uuid.uuid4()
    file_path = os.path.join(user_dir, f"{doc_id}{ext}")
    with open(file_path, "wb") as f:
        f.write(content)

    # 4. Create the Document record
    document = Document(
        id=doc_id,
        user_id=current_user.id,
        filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        status=DocumentStatus.PENDING,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # 5. Queue the background processing
    # In production, use ARQ or Celery. For now, we can use BackgroundTasks.
    from fastapi import BackgroundTasks
    # (BackgroundTasks is a FastAPI feature, see below)

    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> list[DocumentResponse]:
    """List the current user's documents."""
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    documents = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in documents]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document and all its chunks."""
    document = await db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete the file
    try:
        os.remove(document.file_path)
    except FileNotFoundError:
        pass  # Already gone

    # Delete the chunks from the vector store
    from app.services.llm.vector_store import delete_document_chunks
    delete_document_chunks(str(document_id))

    # Delete the record
    await db.delete(document)
    await db.commit()
```

## 8.9 Background Processing (the right way)

The upload endpoint returns instantly, but processing the PDF takes time. We need a background task.

**Two options:**

| Tool | When to use |
|------|-------------|
| FastAPI `BackgroundTasks` | Simple, runs in same process, no retries, dies with the app |
| ARQ (or Celery) | Production, separate worker process, retries, monitoring |

For now, let's use ARQ since you said "production-grade":

```bash
pip install arq
```

```python
# app/workers/arq_worker.py
"""
ARQ worker — runs background jobs in a separate process.

We use ARQ because:
- Built on Redis (which you probably want anyway)
- Async, fast, lightweight
- Has retries built in
- Way simpler than Celery
"""

from arq.connections import RedisSettings
from arq import cron_jobs  # If you want scheduled jobs

from app.config import settings
from app.workers.pdf_processor import process_document_sync


async def process_document_task(ctx, document_id: str):
    """
    The background job that processes a document.

    ARQ calls this with (ctx, *args). `ctx` has the job context.
    """
    # Get a fresh DB session for this job
    from app.db.session import AsyncSessionLocal
    from app.db.models.document import Document
    import uuid

    async with AsyncSessionLocal() as db:
        document = await db.get(Document, uuid.UUID(document_id))
        if not document:
            return  # Was deleted before we got to it

        # Run the processing
        await process_document(document, db)


# Worker settings
class WorkerSettings:
    functions = [process_document_task]  # Functions ARQ can call
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10  # How many jobs to run in parallel
    job_timeout = 600  # 10 minutes max per job
    keep_result = 3600  # Keep job results for 1 hour (for debugging)
```

```python
# app/workers/pdf_processor.py (add the async version)
async def process_document(document: Document, db: AsyncSession) -> None:
    """Async version of the processor, takes an existing session."""
    try:
        document.status = DocumentStatus.PROCESSING
        await db.commit()

        pages = extract_text_from_pdf(document.file_path)
        chunks = split_pages_into_chunks(pages)

        texts = [c["text"] for c in chunks]
        metadata = [
            {"page_number": c["page_number"], "filename": document.filename}
            for c in chunks
        ]
        add_document_chunks(
            user_id=str(document.user_id),
            document_id=str(document.id),
            chunks=texts,
            metadata=metadata,
        )

        document.status = DocumentStatus.READY
        document.chunk_count = len(chunks)
        await db.commit()
    except Exception as e:
        document.status = DocumentStatus.FAILED
        document.error_message = str(e)
        await db.commit()
        raise
```

To enqueue a job from the upload endpoint:

```python
# In the upload endpoint, after creating the document:
from arq.connections import create_pool
from app.config import settings

# Create a Redis connection pool
async def enqueue_document_processing(document_id: str):
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await redis.enqueue_job("process_document_task", document_id)
    await redis.close()

# Call it:
# await enqueue_document_processing(str(document.id))
```

To run the worker:

```bash
arq app.workers.arq_worker.WorkerSettings
```

## 8.10 RAG Quality Improvements (the pro moves)

Basic RAG works. Production RAG is an art. Here are the upgrades:

### 1. Better chunking
- **Semantic chunking** (split where the topic changes, not every N chars)
- **Smaller chunks with overlap** for precise retrieval
- **Document-aware** chunking (respect markdown headers, code blocks)

### 2. Hybrid search
Combine vector search (semantic) with keyword search (BM25):

```python
# langchain.retrievers import EnsembleRetriever
# from langchain_community.retrievers import BM25Retriever
#
# vector_retriever = vector_store.as_retriever()
# bm25_retriever = BM25Retriever.from_documents(docs)
# ensemble = EnsembleRetriever(retrievers=[vector_retriever, bm25_retriever], weights=[0.5, 0.5])
```

### 3. Reranking
After retrieval, use a smaller model to re-score the top results. This often gives huge quality boosts.

```python
# from langchain_cohere import CohereRerank  # paid
# or use a local reranker:
# from langchain.retrievers import ContextualCompressionRetriever
```

### 4. Query rewriting
Before searching, rewrite the user's question to be more searchable. E.g., "what about that thing we discussed" → "what is the return policy for electronics"

```python
# Use the LLM itself to rewrite the query
rewrite_prompt = ChatPromptTemplate.from_template(
    "Given the chat history and the latest user question, "
    "rewrite the question to be standalone and searchable. "
    "Just output the rewritten question, nothing else.\n\n"
    "History: {history}\n"
    "Question: {question}\n"
    "Rewritten:"
)
```

### 5. Citations and source tracking
Always return which documents were used. Users don't trust answers without sources.

### 6. The "I don't know" rule
The system prompt must explicitly say: "If the context doesn't contain the answer, say so." Otherwise the LLM will hallucinate.

## 8.11 Quick Recap

You now have:
- A document upload pipeline (PDF → chunks → embeddings → vector store)
- A chat endpoint that uses RAG (search → context → LLM → response)
- Multi-tenant security (filter by user_id)
- Background processing (ARQ + Redis)
- The data models to support all of it

In Part 9 we'll cover the production concerns: testing, logging, rate limiting, and the things that turn a "works on my machine" app into a real product.

---
