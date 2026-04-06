from typing import Dict, Any, List, Optional, Generator, Tuple

from langchain_ollama import OllamaLLM
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from .config import OLLAMA_LLM_MODEL, OLLAMA_BASE_URL
from .vector_store import similarity_search


SYSTEM_TEMPLATE = """
You are an expert shopping assistant.

Rules:
- Use ONLY the provided product context.
- If you cannot answer from the context, say: "I don't know from the provided products."
- Prefer concise, helpful answers.
- When recommending items, include: title (if present), category, price (if available), rating (if available), and parent_asin.

Product context:
{context}

User question:
{question}

Answer:
""".strip()


def _format_docs(docs: List[Document]) -> str:
    lines: List[str] = []
    for d in docs:
        md = d.metadata or {}
        lines.append(
            f"- ASIN: {md.get('parent_asin')} | "
            f"Category: {md.get('main_category')} | "
            f"Price: {md.get('price')} | "
            f"Rating: {md.get('average_rating')} ({md.get('rating_number')})\n"
            f"  Text: {d.page_content}"
        )
    return "\n\n".join(lines)


def _format_docs_with_scores(docs_with_scores: List[Tuple[Document, float]]) -> str:
    lines: List[str] = []
    for d, score in docs_with_scores:
        md = d.metadata or {}
        lines.append(
            f"- ASIN: {md.get('parent_asin')} | "
            f"Category: {md.get('main_category')} | "
            f"Price: {md.get('price')} | "
            f"Rating: {md.get('average_rating')} ({md.get('rating_number')}) | "
            f"Score: {score}\n"
            f"  Text: {d.page_content}"
        )
    return "\n\n".join(lines)


def stream_answer(
    question: str,
    k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> Generator[str, None, None]:
    docs_with_scores = similarity_search(
        query=question, k=k, metadata_filter=metadata_filter
    )
    if not docs_with_scores:
        yield "I don't know from the provided products."
        return

    docs = [d for d, _ in docs_with_scores]
    context = _format_docs(docs)

    prompt = ChatPromptTemplate.from_template(SYSTEM_TEMPLATE)
    llm = OllamaLLM(model=OLLAMA_LLM_MODEL, base_url=OLLAMA_BASE_URL)

    chain = prompt | llm

    # Stream chunks
    for chunk in chain.stream({"context": context, "question": question}):
        # chunk is usually str
        yield chunk


def answer_json(
    question: str,
    k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    docs_with_scores = similarity_search(
        query=question, k=k, metadata_filter=metadata_filter
    )
    if not docs_with_scores:
        return {
            "question": question,
            "answer": "I don't know from the provided products.",
            "recommendations": [],
            "citations": [],
        }

    docs = [d for d, _ in docs_with_scores]
    context = _format_docs_with_scores(docs_with_scores)

    prompt = ChatPromptTemplate.from_template(SYSTEM_TEMPLATE)
    llm = OllamaLLM(model=OLLAMA_LLM_MODEL, base_url=OLLAMA_BASE_URL)
    chain = prompt | llm

    answer = chain.invoke({"context": context, "question": question})

    recommendations: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    for d, score in docs_with_scores:
        md = d.metadata or {}
        recommendations.append(
            {
                "parent_asin": md.get("parent_asin"),
                "title": md.get("title"),
                "main_category": md.get("main_category"),
                "store": md.get("store"),
                "price": md.get("price"),
                "average_rating": md.get("average_rating"),
                "rating_number": md.get("rating_number"),
                "date_first_available": md.get("date_first_available"),
                "image": md.get("image"),
            }
        )
        citations.append(
            {
                "parent_asin": md.get("parent_asin"),
                "score": score,
                "snippet": (d.page_content or "")[:220],
            }
        )

    return {
        "question": question,
        "answer": str(answer).strip(),
        "recommendations": recommendations,
        "citations": citations,
    }
