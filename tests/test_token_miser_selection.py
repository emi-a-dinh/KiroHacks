import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "token-miser" / "src"))

from indexer.core import run_index
from storage.db import Database
from query.selector import select_units
from query.smart import run_ask


def _write_auth_write_fixture(root: Path):
    route_file = root / "apps/api/src/routes/ideas.ts"
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

    service_file = root / "apps/api/src/services/ideaService.ts"
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

    middleware_file = root / "apps/api/src/middleware/requireAuth.ts"
    middleware_file.parent.mkdir(parents=True)
    middleware_file.write_text(
        """export function requireAuth(req, res, next) {
  req.user = { id: "user_1" };
  return next();
}
""",
        encoding="utf-8",
    )

    rate_limit_file = root / "apps/api/src/middleware/rateLimit.ts"
    rate_limit_file.write_text(
        """export function rateLimit() {
  return (_req, _res, next) => next();
}
""",
        encoding="utf-8",
    )

    typing_file = root / "apps/api/src/types/express.d.ts"
    typing_file.parent.mkdir(parents=True)
    typing_file.write_text(
        """declare global {
  namespace Express {
    interface Request {
      user?: { id: string };
    }
  }
}
""",
        encoding="utf-8",
    )

    frontend_hook = root / "apps/web/src/hooks/useAuth.ts"
    frontend_hook.parent.mkdir(parents=True)
    frontend_hook.write_text(
        """export function useAuth() {
  return { login: async () => undefined };
}
""",
        encoding="utf-8",
    )

    frontend_page = root / "apps/web/src/pages/LoginPage.tsx"
    frontend_page.parent.mkdir(parents=True)
    frontend_page.write_text(
        """export function LoginPage() {
  return null;
}
""",
        encoding="utf-8",
    )

    shared_user = root / "packages/shared/src/types/user.ts"
    shared_user.parent.mkdir(parents=True)
    shared_user.write_text(
        """export interface User {
  id: string;
}
""",
        encoding="utf-8",
    )

    test_file = root / "apps/api/src/routes/ideas.test.ts"
    test_file.write_text(
        """import { ideasRouter } from "./ideas";

test("POST /ideas requires auth", () => {
  expect(ideasRouter).toBeDefined();
});
""",
        encoding="utf-8",
    )


def test_auth_write_task_selects_route_handler_and_service(tmp_path):
    _write_auth_write_fixture(tmp_path)

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
    selected_paths = {item.unit.file_path for item in selection.units}

    assert ("apps/api/src/routes/ideas.ts", "post_root") in selected
    assert ("apps/api/src/middleware/requireAuth.ts", "requireAuth") in selected
    assert any(path.endswith("express.d.ts") for path in selected_paths)
    assert ("apps/api/src/services/ideaService.ts", "createIdea") in selected
    assert any("ideas.test.ts" in path for path in selected_paths)

    assert ("apps/web/src/hooks/useAuth.ts", "useAuth") not in selected
    assert ("apps/web/src/pages/LoginPage.tsx", "LoginPage") not in selected
    assert ("packages/shared/src/types/user.ts", "User") not in selected
    assert ("apps/api/src/middleware/rateLimit.ts", "rateLimit") not in selected


def test_miser_ask_reindexes_when_existing_index_has_no_matches(tmp_path):
    _write_auth_write_fixture(tmp_path)

    stale_index = tmp_path / ".token-miser/index.db"
    with Database(str(stale_index)) as db:
        db.set_metadata("parser_version", "4-route-and-test-units")
        db.commit()

    output = run_ask(
        "Add auth middleware and user attribution before writes, update Post /ideas to requireAuth",
        repo_path=str(tmp_path),
    )

    assert "No relevant code units found" not in output
    assert "apps/api/src/routes/ideas.ts" in output
    assert "post_root" in output
    assert "apps/api/src/middleware/requireAuth.ts" in output
