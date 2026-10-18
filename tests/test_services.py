import io
import threading

import httpx
import pytest
import respx
from pypdf import PdfReader, PdfWriter

from paper_sa.config import Config, Settings
from paper_sa.documents import export_pdf, paper_context, pdf_name, read_pdf
from paper_sa.llm import LLM
from paper_sa.network import ServiceError, public_download, public_url
from paper_sa.pubmed import BASE, PubMed, normalize_query, parse_articles
from paper_sa.store import Store

XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123456</PMID><Article>
<ArticleTitle>A <i>randomized</i> trial</ArticleTitle>
<Journal><ISOAbbreviation>J Med</ISOAbbreviation><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
<Abstract><AbstractText Label="METHODS">120 participants</AbstractText><AbstractText Label="RESULTS">Outcome reported</AbstractText></Abstract>
<AuthorList><Author><LastName>Smith</LastName><Initials>JA</Initials></Author></AuthorList>
<PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
</Article><MeshHeadingList><MeshHeading><DescriptorName>Humans</DescriptorName></MeshHeading></MeshHeadingList>
</MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1000/example</ArticleId><ArticleId IdType="pmc">PMC1234</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("PMID: 33108101, 25029335", "33108101[uid] OR 25029335[uid]"),
        ("https://pubmed.ncbi.nlm.nih.gov/33108101/", "33108101[uid]"),
        ("https://doi.org/10.1056/NEJMoa2026834", '"10.1056/NEJMoa2026834"[AID]'),
        ("PMC1234", "PMC1234[pmc]"),
        ("cancer AND immunotherapy", "cancer AND immunotherapy"),
    ],
)
def test_query_identifiers(query, expected):
    assert normalize_query(query) == expected


def test_parse_structured_pubmed_xml():
    paper = parse_articles(XML)[0]
    assert paper["title"] == "A randomized trial"
    assert paper["year"] == "2024"
    assert paper["authors"] == ["Smith JA"]
    assert "METHODS: 120 participants" in paper["abstract"]
    assert paper["pmcid"] == "PMC1234"
    assert paper["mesh"] == ["Humans"]


@respx.mock
async def test_pubmed_search_and_elink(tmp_path):
    service = PubMed(Config(tmp_path))
    respx.get(BASE + "/esearch.fcgi").mock(
        return_value=httpx.Response(
            200,
            json={
                "esearchresult": {"count": "1", "idlist": ["123456"], "querytranslation": "trial[All Fields]"}
            },
        )
    )
    respx.get(BASE + "/efetch.fcgi").mock(return_value=httpx.Response(200, text=XML))
    result = await service.search("trial")
    assert result["total"] == 1 and result["papers"][0]["pmid"] == "123456"
    respx.get(BASE + "/elink.fcgi").mock(
        return_value=httpx.Response(
            200,
            json={"linksets": [{"linksetdbs": [{"linkname": "pubmed_pubmed_refs", "links": ["123456"]}]}]},
        )
    )
    assert (await service.neighbors("other", "references", 5))[0]["pmid"] == "123456"


@respx.mock
async def test_provider_openai_and_no_secret_in_error(tmp_path):
    config = Config(tmp_path)
    config.save({"api_key": "secret-placeholder"})
    route = respx.post("https://api.openai.com/v1/chat/completions")
    route.mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}))
    assert await LLM(config).complete("question") == "ok"
    assert route.calls.last.request.headers["authorization"] == "Bearer secret-placeholder"
    route.mock(return_value=httpx.Response(401, text="error secret-placeholder"))
    with pytest.raises(ServiceError) as error:
        await LLM(config).complete("question")
    assert "secret-placeholder" not in str(error.value)


@respx.mock
async def test_anthropic_and_ollama(tmp_path):
    config = Config(tmp_path)
    config.save(
        {
            "provider": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
            "model": "test-model",
            "api_key": "placeholder",
        }
    )
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={"content": [{"type": "text", "text": "anthropic ok"}]})
    )
    assert await LLM(config).complete("question") == "anthropic ok"
    assert route.calls.last.request.headers["x-api-key"] == "placeholder"
    config.save({"provider": "ollama", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"})
    route = respx.post("http://127.0.0.1:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "ollama ok"}}]})
    )
    assert await LLM(config).complete("question") == "ollama ok"
    assert "authorization" not in route.calls.last.request.headers


async def test_private_download_destinations_blocked():
    for url in ["http://127.0.0.1/private", "http://[::1]/", "file:///etc/passwd"]:
        with pytest.raises(ServiceError):
            await public_url(url)


@respx.mock
async def test_download_redirect_checks_every_destination(tmp_path, monkeypatch):
    from paper_sa import network

    calls = []

    async def checked(url):
        calls.append(url)
        if "127.0.0.1" in url:
            raise ServiceError("private")

    monkeypatch.setattr(network, "public_url", checked)
    respx.get("https://public.example/paper").mock(
        return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
    )
    with pytest.raises(ServiceError):
        await public_download("https://public.example/paper", tmp_path / "paper.pdf")
    assert len(calls) == 2


def test_context_cites_pdf_pages_and_abstract_fallback(app, paper):
    store = app.state.store
    store.set_pdf(
        paper["id"], "test.pdf", ["Background " * 1000, "Mortality outcome confidence interval. " * 40]
    )
    current = store.paper(paper["id"])
    context = paper_context(store, current, question="mortality confidence", limit=2400)
    assert "[P1 · p.2]" in context["text"]
    assert len(context["text"]) < 2600
    assert "非完整全文" in context["scope"]
    store.set_pdf(paper["id"], "scan.pdf", [""])
    context = paper_context(store, store.paper(paper["id"]))
    assert "未 OCR" in context["scope"]
    assert "[P1 · 摘要]" in context["text"]


def test_pdf_rejects_empty_and_encrypted(tmp_path):
    writer = PdfWriter()
    path = tmp_path / "empty.pdf"
    writer.write(path)
    with pytest.raises(ServiceError):
        read_pdf(path)
    writer.add_blank_page(200, 200)
    writer.encrypt("password")
    writer.write(path)
    with pytest.raises(ServiceError):
        read_pdf(path)


def test_pdf_export_long_table_and_filename(paper):
    markdown = "| Paper | Notes |\n|---|---|\n" + "".join(
        f"| Study {index} | {'研究局限性需要核验。' * 5} |\n" for index in range(70)
    )
    output = export_pdf("中文多页报告", markdown)
    assert len(PdfReader(io.BytesIO(output)).pages) > 1
    paper["metadata"]["title"] = "Bad:/<>* title" * 40
    name = pdf_name(paper)
    assert len(name) < 160
    assert all(character not in name for character in '<>:"/\\|?*')


def test_restart_interrupts_jobs_and_reloads_secrets(tmp_path):
    config = Config(tmp_path)
    config.save({"api_key": "placeholder"})
    assert Config(tmp_path).settings.api_key == "placeholder"
    store = Store(tmp_path / "store.sqlite")
    job = store.create_job("download")
    store.close()
    reopened = Store(tmp_path / "store.sqlite")
    assert reopened.job(job["id"])["status"] == "interrupted"
    reopened.close()


async def test_cancel_report_does_not_save_partial_note(app, paper, monkeypatch):
    cancelled = threading.Event()

    async def answer(*args, **kwargs):
        cancelled.set()
        return "partial"

    monkeypatch.setattr(app.state.llm, "complete", answer)
    job = app.state.store.create_job("report")
    result = await app.state.agents.report(job["id"], cancelled, [paper["id"], paper["id"]], "topic")
    assert result["processed"] == 1
    assert app.state.store.rows("SELECT * FROM notes") == []


def test_bad_remote_api_url():
    with pytest.raises(ValueError):
        Settings(base_url="https://secret:password@example.com/v1")
