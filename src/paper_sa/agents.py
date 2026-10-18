import asyncio
import threading

from .documents import paper_context, pdf_name, read_pdf
from .llm import READING_SYSTEM, SUMMARY
from .network import ServiceError, public_download
from .store import identifier, now


class Agents:
    def __init__(self, store, config, pubmed, llm, browser):
        self.store, self.config, self.pubmed, self.llm, self.browser = store, config, pubmed, llm, browser
        self.tasks = {}
        self.cancellations = {}
        self.download_lock = asyncio.Lock()
        self.chat_locks = {}

    def submit(self, kind, operation, *args):
        job = self.store.create_job(kind)
        cancelled = threading.Event()
        self.cancellations[job["id"]] = cancelled

        async def run():
            try:
                self.progress(job["id"], 1, "任务已启动")
                result = await operation(job["id"], cancelled, *args)
                if cancelled.is_set():
                    self.store.update_job(job["id"], "cancelled", 0, "已取消；已保存的部分结果保留", result)
                else:
                    needs_action = bool(result.get("needs_action"))
                    self.store.update_job(
                        job["id"],
                        "needs_action" if needs_action else "completed",
                        100,
                        "部分论文需要人工登录或导入" if needs_action else "任务完成",
                        result,
                    )
            except asyncio.CancelledError:
                self.store.update_job(job["id"], "interrupted", 0, "任务中断，可重新执行")
            except ServiceError as error:
                self.store.update_job(job["id"], "failed", 0, str(error))
            except Exception:
                self.store.update_job(
                    job["id"], "failed", 0, "任务执行失败，请检查网络、模型配置或文件后重试"
                )
            finally:
                self.tasks.pop(job["id"], None)
                self.cancellations.pop(job["id"], None)

        self.tasks[job["id"]] = asyncio.create_task(run())
        return job

    def progress(self, job_id, progress, message, result=None):
        self.store.update_job(job_id, "running", progress, message, result)

    def cancel(self, job_id):
        if job_id in self.cancellations:
            self.cancellations[job_id].set()
        return self.store.job(job_id)

    async def shutdown(self):
        for cancellation in self.cancellations.values():
            cancellation.set()
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        await self.browser.close()

    async def chat(self, paper, question, summarize=False):
        lock = self.chat_locks.setdefault(paper["id"], asyncio.Lock())
        async with lock:
            context = paper_context(
                self.store, paper, "" if summarize else question, self.config.settings.context_chars
            )
            prompt = SUMMARY if summarize else question
            history = [] if summarize else self.store.messages(paper["id"])
            answer = await self.llm.complete(
                f"<paper_evidence>\n{context['text']}\n</paper_evidence>\n\n问题：{prompt}",
                history,
                system=READING_SYSTEM,
            )
            self.store.add_message(
                paper["id"], "user", "按医学论文结构总结" if summarize else question, context["scope"]
            )
            self.store.add_message(paper["id"], "assistant", answer, context["scope"])
            return {"answer": answer, "scope": context["scope"], "pages": context["pages"]}

    async def snowball(self, job_id, cancelled, seed_ids, relations, depth, per_seed, max_papers):
        frontier = seed_ids
        visited = set(seed_ids)
        discovered = []
        reached_depth = 0
        for level in range(depth):
            reached_depth = level + 1
            next_frontier = []
            for index, source_id in enumerate(frontier):
                if cancelled.is_set() or len(discovered) >= max_papers:
                    break
                source = self.store.paper(source_id)
                if not source["pmid"]:
                    continue
                self.progress(
                    job_id,
                    min(95, int((level + index / max(1, len(frontier))) / depth * 100)),
                    f"第 {level + 1} 跳 · PMID {source['pmid']} · 已发现 {len(discovered)} 篇",
                )
                for relation in relations:
                    if cancelled.is_set() or len(discovered) >= max_papers:
                        break
                    for metadata in await self.pubmed.neighbors(source["pmid"], relation, per_seed):
                        if cancelled.is_set() or len(discovered) >= max_papers:
                            break
                        paper = self.store.upsert_paper(metadata)
                        self.store.edge(source_id, paper["id"], relation)
                        if paper["id"] not in visited:
                            visited.add(paper["id"])
                            discovered.append(paper["id"])
                            next_frontier.append(paper["id"])
            frontier = next_frontier
            if not frontier or cancelled.is_set() or len(discovered) >= max_papers:
                break
        self.store.add_search(
            "snowball",
            {"seed_ids": seed_ids, "relations": relations, "depth": depth, "discovered": discovered},
        )
        return {"paper_ids": discovered, "depth": reached_depth, "needs_action": False}

    async def download(self, job_id, cancelled, paper_ids):
        results = []
        async with self.download_lock:
            papers = sorted(
                [self.store.paper(paper_id) for paper_id in paper_ids],
                key=lambda paper: (
                    not bool(paper["metadata"].get("pmcid")),
                    (paper.get("doi") or "").split("/")[0],
                ),
            )
            for index, paper in enumerate(papers):
                if cancelled.is_set():
                    break
                self.progress(
                    job_id,
                    int(index / len(papers) * 100),
                    f"下载 {index + 1}/{len(papers)} · {paper['metadata']['title'][:65]}",
                    {"papers": results},
                )
                if paper["has_pdf"]:
                    results.append({"paper_id": paper["id"], "status": "existing", "route": "本地已存在"})
                    continue
                temporary = self.config.root / "staging" / f"{identifier()}.pdf"
                route_used = None
                try:
                    routes = await self.pubmed.routes(paper["metadata"])
                    for route in [route for route in routes if route["kind"] == "oa"][:3]:
                        if cancelled.is_set():
                            break
                        try:
                            await public_download(route["url"], temporary)
                            await asyncio.to_thread(read_pdf, temporary)
                            route_used = route["label"]
                            break
                        except Exception:
                            temporary.unlink(missing_ok=True)
                    if not route_used and routes and not cancelled.is_set():
                        self.store.update_job(
                            job_id,
                            "waiting_user",
                            int(index / len(papers) * 100),
                            f"浏览器下载中（{index + 1}/{len(papers)}）：如遇登录/验证码，请在浏览器中手动完成",
                            {"papers": results},
                        )
                        route_used = await self.browser.download(routes, temporary, cancelled)
                    if route_used and not cancelled.is_set():
                        pages = await asyncio.to_thread(read_pdf, temporary)
                        filename = pdf_name(paper)
                        temporary.replace(self.config.root / "papers" / filename)
                        self.store.set_pdf(paper["id"], filename, pages)
                        results.append({"paper_id": paper["id"], "status": "downloaded", "route": route_used})
                    else:
                        results.append(
                            {
                                "paper_id": paper["id"],
                                "status": "needs_user",
                                "message": "未获得 PDF；请手动登录/下载并导入，或重试",
                            }
                        )
                except ServiceError as error:
                    results.append({"paper_id": paper["id"], "status": "needs_user", "message": str(error)})
                finally:
                    temporary.unlink(missing_ok=True)
                await asyncio.sleep(1)
        return {"papers": results, "needs_action": any(item["status"] == "needs_user" for item in results)}

    async def report(self, job_id, cancelled, paper_ids, topic):
        cards = []
        references = []
        sources = []
        for index, paper_id in enumerate(paper_ids, 1):
            if cancelled.is_set():
                return {"processed": len(cards)}
            paper = self.store.paper(paper_id)
            label = f"P{index}"
            context = paper_context(
                self.store, paper, limit=min(self.config.settings.context_chars, 20000), label=label
            )
            self.progress(
                job_id,
                int((index - 1) / (len(paper_ids) + 1) * 100),
                f"提取证据 {index}/{len(paper_ids)} · {paper['metadata']['title'][:60]}",
            )
            card = await self.llm.complete(
                f"{context['text']}\n\n围绕主题：{topic}\n提取精简证据卡（不超过 700 中文字）：PICO、设计、样本量、结果、局限性、证据范围。沿用 [{label}] 来源编号与页码；不确定内容明确标注。"
            )
            cards.append(f"## [{label}]\n{card[:7000]}")
            metadata = paper["metadata"]
            references.append(
                f"- [{label}] {metadata.get('title', '')}. {metadata.get('journal', '')}, {metadata.get('year', '')}. PMID: {paper['pmid'] or '无'}; DOI: {paper['doi'] or '无'}. 证据范围：{context['scope']}"
            )
            sources.append(
                {
                    "label": label,
                    "paper_id": paper_id,
                    "scope": context["scope"],
                    "pages": context["pages"],
                    "evidence_card": card,
                }
            )
        if cancelled.is_set():
            return {"processed": len(cards)}
        self.progress(job_id, 90, "比较证据、梳理分歧并生成综述初稿")
        answer = await self.llm.complete(
            f"主题：{topic}\n以下是独立论文证据卡：\n"
            + "\n\n".join(cards)
            + "\n请生成叙述性综述初稿：摘要、背景、文献来源说明、研究特征比较表、主题综合、结论分歧与可能原因、"
            "证据质量与局限性、研究空白、结论。沿用 [P1] 等来源编号，不新增文献，不编造 PRISMA 筛选数，"
            "不进行未经计算的 meta 分析；明确这是用户选定文献的初步比较。参考文献由程序追加，无需输出。"
        )
        if cancelled.is_set():
            return {"processed": len(cards)}
        content = (
            f"> 叙述性综述初稿 · {now()[:10]} · 共 {len(paper_ids)} 篇用户选定文献。AI 辅助生成，"
            "尚未经独立文献筛选、偏倚评估和事实核验；不等同于系统综述或医学建议。\n\n"
            + answer
            + "\n\n## 已选文献与证据范围\n\n"
            + "\n".join(references)
        )
        searches = self.store.rows(
            "SELECT query,details,created_at FROM searches ORDER BY created_at DESC LIMIT 30"
        )
        note = self.store.create_note(
            topic + " · 综述初稿",
            content,
            kind="report",
            metadata={"sources": sources, "search_history": searches, "generated_at": now()},
        )
        return {"note_id": note["id"], "paper_ids": paper_ids}
