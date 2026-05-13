from fastapi import APIRouter
from . import projects, topics, scripts, characters, scenes, generation, quality, seo, music, publish, approvals, pipeline

router = APIRouter()

router.include_router(projects.router,    prefix="/projects",    tags=["Projects"])
router.include_router(topics.router,      prefix="/topics",      tags=["Topics"])
router.include_router(scripts.router,     prefix="/scripts",     tags=["Scripts"])
router.include_router(characters.router,  prefix="/characters",  tags=["Characters"])
router.include_router(scenes.router,      prefix="/scenes",      tags=["Scenes"])
router.include_router(generation.router,  prefix="/generation",  tags=["Generation"])
router.include_router(quality.router,     prefix="/quality",     tags=["Quality"])
router.include_router(seo.router,         prefix="/seo",         tags=["SEO"])
router.include_router(music.router,       prefix="/music",       tags=["Music"])
router.include_router(publish.router,     prefix="/publish",     tags=["Publish"])
router.include_router(approvals.router,   prefix="/approvals",   tags=["Approvals"])
router.include_router(pipeline.router,    prefix="/pipeline",    tags=["Pipeline (LangGraph)"])
