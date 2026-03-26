"""
agents/blog.py
Blog automation agents for The Moon ecosystem.
Contains: BlogManagerAgent, BlogWriterAgent, BlogPublisherAgent, DirectWriterAgent
"""
import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional
from core.agent_base import AgentBase, TaskResult
from core.observability import observe_agent


logger = logging.getLogger(__name__)


@observe_agent
class BlogManagerAgent(AgentBase):
    """
    Coordinates the blog creation process.
    Manages: writer, publisher, and post lifecycle.
    """
    AGENT_ID = "blog_manager"

    def __init__(self):
        super().__init__()
        self.name = "BlogManagerAgent"
        self.description = "Manages the blog creation workflow"
        self.writer = BlogWriterAgent()
        self.publisher = BlogPublisherAgent()
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute blog management task.
        task: 'write_and_publish', 'manage_post', 'update_blog'
        kwargs: topic, content, metadata, etc.
        """
        start = time.time()
        try:
            if task in ['write_and_publish', 'create']:
                topic = kwargs.get('topic', '')
                if not topic:
                    return TaskResult(success=False, error="Missing topic for blog creation")

                # Write the blog post
                write_result = await self.writer._execute(
                    task='write',
                    topic=topic,
                    **kwargs
                )
                if not write_result.success:
                    return TaskResult(
                        success=False,
                        error=f"Failed to write blog: {write_result.error}",
                        execution_time=time.time() - start
                    )

                # Publish the blog post
                content = write_result.data.get('content', '')
                metadata = write_result.data.get('metadata', {})
                metadata.update(kwargs)  # merge additional metadata from kwargs

                publish_result = await self.publisher._execute(
                    task='publish',
                    content=content,
                    **metadata
                )
                if not publish_result.success:
                    return TaskResult(
                        success=False,
                        error=f"Failed to publish blog: {publish_result.error}",
                        execution_time=time.time() - start
                    )

                return TaskResult(
                    success=True,
                    data={
                        "write_result": write_result.data,
                        "publish_result": publish_result.data,
                        "status": "published"
                    },
                    execution_time=time.time() - start
                )

            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown task: {task}",
                    execution_time=time.time() - start
                )
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )


@observe_agent
class BlogWriterAgent(AgentBase):
    """
    Generates blog post content using LLMs.
    Creates structured, SEO-friendly blog posts.
    """
    AGENT_ID = "blog_writer"

    def __init__(self):
        super().__init__()
        self.name = "BlogWriterAgent"
        self.description = "Writes blog posts with structured content"
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute blog writing task.
        task: 'write', 'draft', 'outline'
        kwargs: topic, keywords, tone, length, etc.
        """
        start = time.time()
        try:
            if task in ['write', 'draft']:
                topic = kwargs.get('topic', '')
                if not topic:
                    return TaskResult(success=False, error="Missing topic for blog writing")

                # Import LLM router to generate content
                from agents.llm import LLMRouter
                llm = LLMRouter()

                # Prepare the prompt based on requirements
                language = kwargs.get('language', 'pt-BR')
                length = kwargs.get('length', kwargs.get('max_words', 800))
                keywords = kwargs.get('keywords', [])
                tone = kwargs.get('tone', 'informative')
                audience = kwargs.get('audience', 'general')
                avoid_context = kwargs.get('avoid_context', '')

                prompt_parts = [
                    f"Write a blog post in {language} about: {topic}",
                    f"Audience: {audience}",
                    f"Tone: {tone}",
                    f"Length: approximately {length} words",
                    f"Format: Markdown with H2 headers",
                ]

                if keywords:
                    prompt_parts.append(f"Include these keywords: {', '.join(keywords)}")

                if avoid_context:
                    prompt_parts.append(f"Avoid: {avoid_context}")

                prompt_parts.append("\nWrite the complete blog post:")

                prompt = "\n".join(prompt_parts)

                # Generate the content
                content = await llm.complete(prompt, task_type="blog_writing", actor="blog_agent")

                if not content or len(content.strip()) < 100:
                    return TaskResult(
                        success=False,
                        error="Generated content too short",
                        execution_time=time.time() - start
                    )

                # Create metadata
                metadata = {
                    "title": topic,
                    "topic": topic,
                    "language": language,
                    "length_target": length,
                    "keywords": keywords,
                    "tone": tone,
                    "audience": audience,
                    "generated_at": time.time(),
                    "source": "BlogWriterAgent",
                }

                return TaskResult(
                    success=True,
                    data={
                        "content": content,
                        "metadata": metadata,
                        "word_count": len(content.split()),
                        "status": "written"
                    },
                    execution_time=time.time() - start
                )

            elif task == 'outline':
                topic = kwargs.get('topic', '')
                if not topic:
                    return TaskResult(success=False, error="Missing topic for outline")

                # Generate an outline instead of full content
                from agents.llm import LLMRouter
                llm = LLMRouter()

                prompt = f"""
                Create a detailed outline for a blog post about: {topic}
                Provide 4-6 main sections with H2 headers (# Header) and brief descriptions.
                Format as Markdown.
                """

                outline = await llm.complete(prompt, task_type="blog_outlining", actor="blog_agent")

                return TaskResult(
                    success=True,
                    data={
                        "outline": outline,
                        "topic": topic,
                        "status": "outlined"
                    },
                    execution_time=time.time() - start
                )

            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown task: {task}",
                    execution_time=time.time() - start
                )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )


@observe_agent
class BlogPublisherAgent(AgentBase):
    """
    Publishes blog posts to the static site generator.
    Handles: file creation, HTML generation, asset management.
    """
    AGENT_ID = "blog_publisher"

    def __init__(self):
        super().__init__()
        self.name = "BlogPublisherAgent"
        self.description = "Publishes blog posts to the static site"
        self.logger = logging.getLogger(self.__class__.__name__)
        # Define the posts directory
        self.posts_dir = Path("meu_blog_autonomo/posts_md")
        self.posts_dir.mkdir(parents=True, exist_ok=True)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute blog publishing task.
        task: 'publish', 'update', 'create_post'
        kwargs: content, title, date, tags, etc.
        """
        start = time.time()
        try:
            if task in ['publish', 'create_post']:
                content = kwargs.get('content', '')
                if not content:
                    return TaskResult(success=False, error="Missing content for publishing")

                # Extract or create title
                title = kwargs.get('title', kwargs.get('topic', 'Untitled'))
                
                # Create filename from title (remove special chars, replace spaces with underscores)
                filename_title = "".join(c if c.isalnum() or c in ' _-' else '_' for c in title)
                filename_title = filename_title.replace(' ', '_').replace('__', '_').strip('_')
                filename = f"{filename_title}.md"

                # Create the post file path
                file_path = self.posts_dir / filename
                
                # Add frontmatter to the content
                tags = kwargs.get('tags', [])
                language = kwargs.get('language', 'pt-BR')
                date = kwargs.get('date', time.strftime('%Y-%m-%d'))
                
                frontmatter = f"""---
title: "{title}"
date: {date}
tags: [{', '.join([f'"{tag}"' for tag in tags])}]
language: {language}
---

"""
                
                full_content = frontmatter + content

                # Write the content to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(full_content)

                self.logger.info(f"Published blog post: {file_path}")

                return TaskResult(
                    success=True,
                    data={
                        "file_path": str(file_path),
                        "title": title,
                        "filename": filename,
                        "status": "published",
                        "tags": tags,
                        "language": language
                    },
                    execution_time=time.time() - start
                )

            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown task: {task}",
                    execution_time=time.time() - start
                )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )


@observe_agent
class DirectWriterAgent(AgentBase):
    """
    Simplified blog writer for quick content generation.
    Less structured than BlogWriterAgent, for faster turnaround.
    """
    AGENT_ID = "direct_writer"

    def __init__(self):
        super().__init__()
        self.name = "DirectWriterAgent"
        self.description = "Quick blog content generation"
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute direct writing task.
        task: 'write', 'quick_write'
        kwargs: topic, content_type, etc.
        """
        start = time.time()
        try:
            if task in ['write', 'quick_write']:
                topic = kwargs.get('topic', '')
                if not topic:
                    return TaskResult(success=False, error="Missing topic for direct writing")

                # Import LLM router to generate content
                from agents.llm import LLMRouter
                llm = LLMRouter()

                content_type = kwargs.get('content_type', 'blog_post')
                length = kwargs.get('length', kwargs.get('max_words', 500))

                prompt = f"""
                Write a {content_type} about: {topic}
                Keep it to approximately {length} words.
                Make it engaging and well-structured.
                """

                content = await llm.complete(prompt, task_type="direct_writing", actor="blog_agent")

                if not content or len(content.strip()) < 50:
                    return TaskResult(
                        success=False,
                        error="Generated content too short",
                        execution_time=time.time() - start
                    )

                return TaskResult(
                    success=True,
                    data={
                        "content": content,
                        "topic": topic,
                        "status": "written"
                    },
                    execution_time=time.time() - start
                )

            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown task: {task}",
                    execution_time=time.time() - start
                )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )