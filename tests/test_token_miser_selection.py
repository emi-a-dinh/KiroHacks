import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "token-miser" / "src"))

from indexer.core import run_index
from storage.db import Database
from query.selector import select_units


def test_auth_write_task_selects_route_handler_and_service(tmp_path):
    route_file = tmp_path / "apps/api/src/routes/ideas.ts"
    route_file.parent.mkdir(parents=True)
    route_file.write_text(
        """import { Router } from "express";
import { requireAuth } from "../middleware/requireAuth";
import { createIdea, getIdea, listIdeas } from "../services/ideaService";

export const ideasRouter = Router();

ideasRouter.get("/", requireAuth, (req, res, next) => {
  try {
    res.json(listIdeas(req.query));
  } catch (error) {
    next(error);
  }
});

// BUG-001: This write endpoint should require auth before accepting feedback.
ideasRouter.post("/", (req, res, next) => {
  try {
    res.status(201).json(createIdea(req.body));
  } catch (error) {
    next(error);
  }
});
""",
        encoding="utf-8",
    )

    service_file = tmp_path / "apps/api/src/services/ideaService.ts"
    service_file.parent.mkdir(parents=True)
    service_file.write_text(
        """import { addIdea } from "../repositories/inMemoryStore";

export function createIdea(input: unknown) {
  return addIdea(input);
}

export function listIdeas(filters = {}) {
  return [];
}
""",
        encoding="utf-8",
    )

    middleware_file = tmp_path / "apps/api/src/middleware/requireAuth.ts"
    middleware_file.parent.mkdir(parents=True)
    middleware_file.write_text(
        """export function requireAuth(req, res, next) {
  req.user = { id: "user_1" };
  return next();
}
""",
        encoding="utf-8",
    )

    result = run_index(str(tmp_path))

    with Database(result.index_path) as db:
        selection = select_units(
            db,
            "Add auth middleware and user attribution before writes",
            k=10,
            include_neighbors=True,
            include_tests=True,
        )

    selected = {(item.unit.file_path, item.unit.symbol_name) for item in selection.units}

    assert ("apps/api/src/routes/ideas.ts", "post_root") in selected
    assert ("apps/api/src/services/ideaService.ts", "createIdea") in selected
    assert selection.coverage["write_endpoint_found"] is True
    assert selection.confidence_label == "high"
