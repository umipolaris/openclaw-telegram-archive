"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Braces,
  CircleAlert,
  FileText,
  Files,
  History,
  ListFilter,
  Pencil,
  Plus,
  RefreshCcw,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { apiFetch, apiGet, apiPost } from "@/lib/api-client";
import { getCurrentUser, type UserRole } from "@/lib/auth";
import { userRoleLabel } from "@/lib/labels";

type RulesetSummary = {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
};

type RuleVersionSummary = {
  id: string;
  ruleset_id: string;
  version_no: number;
  is_active: boolean;
  published_at: string | null;
  created_at: string;
};

type RulesetsListResponse = {
  items: RulesetSummary[];
};

type RulesetDetailResponse = {
  ruleset: RulesetSummary;
  versions: RuleVersionSummary[];
};

type RuleVersionDetailResponse = {
  id: string;
  ruleset_id: string;
  version_no: number;
  rules_json: Record<string, unknown>;
  checksum_sha256: string;
  is_active: boolean;
  published_at: string | null;
  created_at: string;
};

type RuleTestResponse = {
  category: string;
  tags: string[];
  event_date: string | null;
  review_needed: boolean;
};

type BackfillAcceptedResponse = {
  job_id: string;
  status: string;
};

type RulesetExportResponse = {
  ruleset: RulesetSummary;
  versions: RuleVersionDetailResponse[];
};

type RulesImportResponse = {
  ruleset_id: string;
  imported_versions: number;
  activated_version_id: string | null;
};

type RuleSimulationSample = {
  document_id: string;
  title: string;
  current_category: string | null;
  predicted_category: string;
  current_event_date: string | null;
  predicted_event_date: string | null;
  current_tags: string[];
  predicted_tags: string[];
  changed: boolean;
  changed_fields: string[];
};

type RuleSimulationResponse = {
  rule_version_id: string;
  baseline_rule_version_id: string | null;
  scanned: number;
  changed: number;
  unchanged: number;
  samples: RuleSimulationSample[];
  generated_at: string;
};

type RuleConflictItem = {
  source_field: string;
  keyword: string;
  categories: string[];
};

type RuleConflictResponse = {
  rule_version_id: string;
  total_conflicts: number;
  conflicts: RuleConflictItem[];
};

type RuleTestSampleInput = {
  caption: string;
  title: string;
  description: string;
  filename: string;
  body_text: string;
};

type RuleKeywordField = "title" | "description" | "filename" | "body";

type CategoryRuleForm = {
  id: string;
  category: string;
  titleKeywords: string;
  descriptionKeywords: string;
  filenameKeywords: string;
  bodyKeywords: string;
  tags: string;
};

type TagCategoryRuleForm = {
  id: string;
  category: string;
  tags: string;
  match: "any" | "all";
};

type RulesFormState = {
  defaultCategory: string;
  categoryRules: CategoryRuleForm[];
  tagCategoryRules: TagCategoryRuleForm[];
};

const DEFAULT_RULES = {
  default_category: "기타",
  category_rules: [
    {
      category: "회의",
      keywords: { title: ["회의"], description: ["회의록"] },
      tags: ["회의"],
    },
  ],
};

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString("ko-KR");
}

function parseRulesJson(text: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("rules_json은 JSON object 여야 합니다.");
  }
  return parsed as Record<string, unknown>;
}

function normalizeImportVersions(parsed: unknown): unknown[] {
  if (Array.isArray(parsed)) return parsed;
  if (parsed && typeof parsed === "object" && Array.isArray((parsed as { versions?: unknown[] }).versions)) {
    return (parsed as { versions: unknown[] }).versions;
  }
  throw new Error("import JSON 형식은 배열 또는 {\"versions\":[...]} 이어야 합니다.");
}

function toNullableText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function localId(): string {
  return `row_${Math.random().toString(36).slice(2, 10)}`;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of value) {
    const token = String(raw ?? "").trim();
    if (!token) continue;
    const key = token.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(token);
  }
  return out;
}

function parseTokenListInput(value: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of value.split(/[,\n]/g)) {
    const token = raw.trim();
    if (!token) continue;
    const key = token.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(token);
  }
  return out;
}

function joinTokenList(tokens: string[]): string {
  return tokens.join(", ");
}

function emptyCategoryRuleForm(): CategoryRuleForm {
  return {
    id: localId(),
    category: "",
    titleKeywords: "",
    descriptionKeywords: "",
    filenameKeywords: "",
    bodyKeywords: "",
    tags: "",
  };
}

function emptyTagCategoryRuleForm(): TagCategoryRuleForm {
  return {
    id: localId(),
    category: "",
    tags: "",
    match: "any",
  };
}

function parseRulesJsonToForm(rulesJson: Record<string, unknown>): RulesFormState {
  const defaultCategoryRaw = rulesJson.default_category;
  const defaultCategory = typeof defaultCategoryRaw === "string" && defaultCategoryRaw.trim() ? defaultCategoryRaw.trim() : "기타";

  const categoryRulesRaw = Array.isArray(rulesJson.category_rules) ? rulesJson.category_rules : [];
  const categoryRules: CategoryRuleForm[] = categoryRulesRaw
    .filter((row): row is Record<string, unknown> => isPlainObject(row))
    .map((row) => {
      const keywords = isPlainObject(row.keywords) ? row.keywords : {};
      return {
        id: localId(),
        category: String(row.category ?? "").trim(),
        titleKeywords: joinTokenList(toStringArray(keywords.title)),
        descriptionKeywords: joinTokenList(toStringArray(keywords.description)),
        filenameKeywords: joinTokenList(toStringArray(keywords.filename)),
        bodyKeywords: joinTokenList(toStringArray(keywords.body)),
        tags: joinTokenList(toStringArray(row.tags)),
      };
    });

  const tagCategoryRulesRaw = Array.isArray(rulesJson.tag_category_rules) ? rulesJson.tag_category_rules : [];
  const tagCategoryRules: TagCategoryRuleForm[] = tagCategoryRulesRaw
    .filter((row): row is Record<string, unknown> => isPlainObject(row))
    .map((row) => {
      const rawMatch = String(row.match ?? "any").trim().toLowerCase();
      return {
        id: localId(),
        category: String(row.category ?? "").trim(),
        tags: joinTokenList(toStringArray(row.tags)),
        match: rawMatch === "all" ? "all" : "any",
      };
    });

  return {
    defaultCategory,
    categoryRules,
    tagCategoryRules,
  };
}

function buildRulesJsonFromForm(form: RulesFormState): Record<string, unknown> {
  const categoryRules = form.categoryRules
    .map((row) => {
      const category = row.category.trim();
      if (!category) return null;

      const keywords: Record<string, string[]> = {};
      const titleKeywords = parseTokenListInput(row.titleKeywords);
      const descriptionKeywords = parseTokenListInput(row.descriptionKeywords);
      const filenameKeywords = parseTokenListInput(row.filenameKeywords);
      const bodyKeywords = parseTokenListInput(row.bodyKeywords);
      if (titleKeywords.length) keywords.title = titleKeywords;
      if (descriptionKeywords.length) keywords.description = descriptionKeywords;
      if (filenameKeywords.length) keywords.filename = filenameKeywords;
      if (bodyKeywords.length) keywords.body = bodyKeywords;

      const payload: Record<string, unknown> = {
        category,
      };
      if (Object.keys(keywords).length > 0) payload.keywords = keywords;
      const tags = parseTokenListInput(row.tags);
      if (tags.length) payload.tags = tags;
      return payload;
    })
    .filter((row): row is Record<string, unknown> => Boolean(row));

  const tagCategoryRules = form.tagCategoryRules
    .map((row) => {
      const category = row.category.trim();
      if (!category) return null;
      const tags = parseTokenListInput(row.tags);
      if (tags.length === 0) return null;
      return {
        category,
        tags,
        match: row.match === "all" ? "all" : "any",
      };
    })
    .filter((row): row is { category: string; tags: string[]; match: "any" | "all" } => Boolean(row));

  return {
    default_category: form.defaultCategory.trim() || "기타",
    category_rules: categoryRules,
    tag_category_rules: tagCategoryRules,
  };
}

export function RulesWorkspace() {
  const [userRole, setUserRole] = useState<UserRole | null>(null);
  const [rulesets, setRulesets] = useState<RulesetSummary[]>([]);
  const [selectedRulesetId, setSelectedRulesetId] = useState("");
  const [rulesetDetail, setRulesetDetail] = useState<RulesetDetailResponse | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [versionDetail, setVersionDetail] = useState<RuleVersionDetailResponse | null>(null);
  const [rulesJsonText, setRulesJsonText] = useState(JSON.stringify(DEFAULT_RULES, null, 2));
  const [rulesEditorMode, setRulesEditorMode] = useState<"form" | "json">("form");
  const [rulesForm, setRulesForm] = useState<RulesFormState>(() =>
    parseRulesJsonToForm(DEFAULT_RULES as Record<string, unknown>),
  );

  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [rulesetDescriptionDraft, setRulesetDescriptionDraft] = useState("");
  const [rulesetActiveDraft, setRulesetActiveDraft] = useState(true);

  const [testInput, setTestInput] = useState<RuleTestSampleInput>({
    caption: "주간 운영회의\n다음 액션 정리\n#분류:회의\n#날짜:2026-02-24\n#태그:alpha,beta",
    title: "",
    description: "",
    filename: "meeting_20260224.docx",
    body_text: "",
  });
  const [testResult, setTestResult] = useState<RuleTestResponse | null>(null);
  const [simulationLimit, setSimulationLimit] = useState("200");
  const [simulationResult, setSimulationResult] = useState<RuleSimulationResponse | null>(null);
  const [conflictResult, setConflictResult] = useState<RuleConflictResponse | null>(null);

  const [backfillBatchSize, setBackfillBatchSize] = useState("500");
  const [backfillFrom, setBackfillFrom] = useState("");
  const [backfillTo, setBackfillTo] = useState("");
  const [backfillCategoryId, setBackfillCategoryId] = useState("");
  const [backfillReviewOnly, setBackfillReviewOnly] = useState(false);
  const [lastBackfillJob, setLastBackfillJob] = useState<BackfillAcceptedResponse | null>(null);

  const [exportText, setExportText] = useState("");
  const [importName, setImportName] = useState("");
  const [importDescription, setImportDescription] = useState("");
  const [importActivateLatest, setImportActivateLatest] = useState(true);
  const [importText, setImportText] = useState("");

  const [loadingRulesets, setLoadingRulesets] = useState(true);
  const [loadingRulesetDetail, setLoadingRulesetDetail] = useState(false);
  const [loadingVersionDetail, setLoadingVersionDetail] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const isAdmin = userRole === "ADMIN";
  const versions = useMemo(() => rulesetDetail?.versions ?? [], [rulesetDetail]);

  const selectedRuleset = useMemo(() => {
    return rulesets.find((row) => row.id === selectedRulesetId) ?? null;
  }, [rulesets, selectedRulesetId]);

  const selectedVersion = useMemo(() => {
    return versions.find((row) => row.id === selectedVersionId) ?? null;
  }, [versions, selectedVersionId]);

  const syncRulesJsonFromForm = useCallback((nextForm: RulesFormState) => {
    setRulesForm(nextForm);
    setRulesJsonText(JSON.stringify(buildRulesJsonFromForm(nextForm), null, 2));
  }, []);

  const updateRulesForm = useCallback(
    (updater: (prev: RulesFormState) => RulesFormState) => {
      setRulesForm((prev) => {
        const next = updater(prev);
        setRulesJsonText(JSON.stringify(buildRulesJsonFromForm(next), null, 2));
        return next;
      });
    },
    [],
  );

  const loadRulesets = useCallback(async () => {
    setLoadingRulesets(true);
    try {
      const res = await apiGet<RulesetsListResponse>("/rulesets");
      setRulesets(res.items);
      setSelectedRulesetId((prev) => {
        if (prev && res.items.some((x) => x.id === prev)) return prev;
        return res.items[0]?.id ?? "";
      });
      if (res.items.length === 0) {
        setRulesetDetail(null);
        setSelectedVersionId("");
        setVersionDetail(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "규칙셋 로드 실패");
    } finally {
      setLoadingRulesets(false);
    }
  }, []);

  const loadRulesetDetail = useCallback(async (rulesetId: string) => {
    if (!rulesetId) return;

    setLoadingRulesetDetail(true);
    try {
      const res = await apiGet<RulesetDetailResponse>(`/rulesets/${rulesetId}`);
      setRulesetDetail(res);
      setRulesetDescriptionDraft(res.ruleset.description ?? "");
      setRulesetActiveDraft(res.ruleset.is_active);

      setSelectedVersionId((prev) => {
        if (prev && res.versions.some((x) => x.id === prev)) return prev;
        const active = res.versions.find((x) => x.is_active);
        return active?.id ?? res.versions[0]?.id ?? "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "규칙셋 상세 로드 실패");
      setRulesetDetail(null);
      setSelectedVersionId("");
    } finally {
      setLoadingRulesetDetail(false);
    }
  }, []);

  const loadVersionDetail = useCallback(async (versionId: string) => {
    if (!versionId) return;

    setLoadingVersionDetail(true);
    try {
      const res = await apiGet<RuleVersionDetailResponse>(`/rule-versions/${versionId}`);
      setVersionDetail(res);
      setRulesJsonText(JSON.stringify(res.rules_json, null, 2));
      setRulesForm(parseRulesJsonToForm(res.rules_json ?? {}));
    } catch (err) {
      setError(err instanceof Error ? err.message : "규칙 버전 로드 실패");
      setVersionDetail(null);
    } finally {
      setLoadingVersionDetail(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadInitial() {
      try {
        const user = await getCurrentUser();
        if (!cancelled && user) {
          setUserRole(user.role);
        }
      } catch {
        // ignore
      }
      if (!cancelled) {
        await loadRulesets();
      }
    }

    void loadInitial();
    return () => {
      cancelled = true;
    };
  }, [loadRulesets]);

  useEffect(() => {
    if (!selectedRulesetId) return;
    void loadRulesetDetail(selectedRulesetId);
  }, [loadRulesetDetail, selectedRulesetId]);

  useEffect(() => {
    if (!selectedVersionId) {
      setVersionDetail(null);
      return;
    }
    void loadVersionDetail(selectedVersionId);
  }, [loadVersionDetail, selectedVersionId]);

  const runAction = async (actionKey: string, fn: () => Promise<void>) => {
    setBusyAction(actionKey);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청 실패");
    } finally {
      setBusyAction(null);
    }
  };

  const createRuleset = async () => {
    if (!isAdmin) return;
    const name = createName.trim();
    if (!name) {
      setError("규칙셋 이름을 입력하세요.");
      return;
    }

    await runAction("create-ruleset", async () => {
      const created = await apiPost<RulesetSummary>("/rulesets", {
        name,
        description: toNullableText(createDescription),
      });
      setCreateName("");
      setCreateDescription("");
      await loadRulesets();
      setSelectedRulesetId(created.id);
      setMessage(`규칙셋 생성 완료: ${created.name}`);
    });
  };

  const updateRulesetMeta = async () => {
    if (!isAdmin || !selectedRulesetId) return;

    await runAction("update-ruleset", async () => {
      await apiFetch<RulesetSummary>(`/rulesets/${selectedRulesetId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: toNullableText(rulesetDescriptionDraft),
          is_active: rulesetActiveDraft,
        }),
      });
      await loadRulesets();
      await loadRulesetDetail(selectedRulesetId);
      setMessage("규칙셋 메타 저장 완료");
    });
  };

  const createRuleVersion = async () => {
    if (!isAdmin || !selectedRulesetId) return;

    await runAction("create-version", async () => {
      const rulesJson =
        rulesEditorMode === "json" ? parseRulesJson(rulesJsonText) : buildRulesJsonFromForm(rulesForm);
      const normalized = JSON.stringify(rulesJson, null, 2);
      setRulesJsonText(normalized);
      setRulesForm(parseRulesJsonToForm(rulesJson));
      const created = await apiPost<RuleVersionSummary>(`/rulesets/${selectedRulesetId}/versions`, {
        rules_json: rulesJson,
      });
      await loadRulesetDetail(selectedRulesetId);
      setSelectedVersionId(created.id);
      setMessage(`v${created.version_no} 생성 완료`);
    });
  };

  const activateVersion = async (versionId: string) => {
    if (!isAdmin) return;

    await runAction(`activate-${versionId}`, async () => {
      await apiPost(`/rule-versions/${versionId}/activate`, {});
      if (selectedRulesetId) {
        await loadRulesetDetail(selectedRulesetId);
      }
      setSelectedVersionId(versionId);
      setMessage("규칙 버전 활성화 완료");
    });
  };

  const executeRuleTest = async () => {
    if (!selectedVersionId) {
      setError("테스트할 규칙 버전을 선택하세요.");
      return;
    }

    await runAction("rule-test", async () => {
      const result = await apiPost<RuleTestResponse>("/rules/test", {
        rule_version_id: selectedVersionId,
        sample: {
          caption: toNullableText(testInput.caption),
          title: toNullableText(testInput.title),
          description: toNullableText(testInput.description),
          filename: toNullableText(testInput.filename),
          body_text: toNullableText(testInput.body_text),
        },
      });
      setTestResult(result);
      setMessage("패턴 테스트 실행 완료");
    });
  };

  const runBatchSimulation = async () => {
    if (!selectedVersionId) {
      setError("시뮬레이션할 규칙 버전을 선택하세요.");
      return;
    }
    const parsedLimit = Number(simulationLimit);
    if (!Number.isInteger(parsedLimit) || parsedLimit <= 0) {
      setError("limit은 1 이상의 정수여야 합니다.");
      return;
    }

    await runAction("simulate-batch", async () => {
      const payload: Record<string, unknown> = {
        rule_version_id: selectedVersionId,
        limit: parsedLimit,
      };
      if (backfillCategoryId.trim() || backfillFrom || backfillTo || backfillReviewOnly) {
        payload.filter = {
          ...(backfillCategoryId.trim() ? { category_id: backfillCategoryId.trim() } : {}),
          ...(backfillFrom ? { from: backfillFrom } : {}),
          ...(backfillTo ? { to: backfillTo } : {}),
          ...(backfillReviewOnly ? { review_only: true } : {}),
        };
      }
      const result = await apiPost<RuleSimulationResponse>("/rules/simulate/batch", payload);
      setSimulationResult(result);
      setMessage(`배치 시뮬레이션 완료: 스캔=${result.scanned}, 변경=${result.changed}`);
    });
  };

  const detectConflicts = async () => {
    if (!selectedVersionId) {
      setError("충돌 탐지할 규칙 버전을 선택하세요.");
      return;
    }
    await runAction("detect-conflicts", async () => {
      const result = await apiGet<RuleConflictResponse>(`/rules/conflicts/${selectedVersionId}`);
      setConflictResult(result);
      setMessage(`충돌 탐지 완료: ${result.total_conflicts}건`);
    });
  };

  const triggerBackfill = async () => {
    if (!isAdmin) return;
    if (!selectedVersionId) {
      setError("재처리할 규칙 버전을 선택하세요.");
      return;
    }

    const parsedBatch = Number(backfillBatchSize);
    if (!Number.isInteger(parsedBatch) || parsedBatch <= 0) {
      setError("batch_size는 1 이상의 정수여야 합니다.");
      return;
    }

    await runAction("backfill", async () => {
      const filter: Record<string, unknown> = {};
      if (backfillCategoryId.trim()) filter.category_id = backfillCategoryId.trim();
      if (backfillFrom) filter.from = backfillFrom;
      if (backfillTo) filter.to = backfillTo;
      if (backfillReviewOnly) filter.review_only = true;

      const payload: Record<string, unknown> = {
        rule_version_id: selectedVersionId,
        batch_size: parsedBatch,
      };
      if (Object.keys(filter).length > 0) payload.filter = filter;

      const result = await apiPost<BackfillAcceptedResponse>("/rules/backfill", payload);
      setLastBackfillJob(result);
      setMessage(`백필 요청 완료: 작업 ID=${result.job_id}`);
    });
  };

  const exportRuleset = async () => {
    if (!selectedRulesetId) {
      setError("내보낼 규칙셋을 선택하세요.");
      return;
    }

    await runAction("export-ruleset", async () => {
      const result = await apiGet<RulesetExportResponse>(`/rulesets/${selectedRulesetId}/export`);
      setExportText(JSON.stringify(result, null, 2));
      setMessage("규칙셋 내보내기 완료");
    });
  };

  const importRules = async () => {
    if (!isAdmin) return;
    const name = importName.trim();
    if (!name) {
      setError("가져오기 대상 규칙셋 이름을 입력하세요.");
      return;
    }
    if (!importText.trim()) {
      setError("가져올 JSON을 입력하세요.");
      return;
    }

    await runAction("import-ruleset", async () => {
      const parsed = JSON.parse(importText) as unknown;
      const versions = normalizeImportVersions(parsed);
      const result = await apiPost<RulesImportResponse>("/rules/import", {
        ruleset_name: name,
        description: toNullableText(importDescription),
        versions,
        activate_latest: importActivateLatest,
      });
      await loadRulesets();
      setSelectedRulesetId(result.ruleset_id);
      setMessage(
        `규칙 가져오기 완료: 버전수=${result.imported_versions}, 활성버전=${result.activated_version_id ?? "-"}`,
      );
    });
  };

  const resetRulesTemplate = () => {
    const nextForm = parseRulesJsonToForm(DEFAULT_RULES as Record<string, unknown>);
    syncRulesJsonFromForm(nextForm);
  };

  const applyJsonToForm = () => {
    try {
      const parsed = parseRulesJson(rulesJsonText);
      const nextForm = parseRulesJsonToForm(parsed);
      syncRulesJsonFromForm(nextForm);
      setMessage("JSON을 폼 편집기에 반영했습니다.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "JSON 파싱 실패");
    }
  };

  const addCategoryRuleFormRow = () => {
    updateRulesForm((prev) => ({
      ...prev,
      categoryRules: [...prev.categoryRules, emptyCategoryRuleForm()],
    }));
  };

  const removeCategoryRuleFormRow = (rowId: string) => {
    updateRulesForm((prev) => ({
      ...prev,
      categoryRules: prev.categoryRules.filter((row) => row.id !== rowId),
    }));
  };

  const updateCategoryRuleFormRow = (rowId: string, patch: Partial<CategoryRuleForm>) => {
    updateRulesForm((prev) => ({
      ...prev,
      categoryRules: prev.categoryRules.map((row) => (row.id === rowId ? { ...row, ...patch } : row)),
    }));
  };

  const updateCategoryRuleKeyword = (rowId: string, field: RuleKeywordField, value: string) => {
    if (field === "title") {
      updateCategoryRuleFormRow(rowId, { titleKeywords: value });
      return;
    }
    if (field === "description") {
      updateCategoryRuleFormRow(rowId, { descriptionKeywords: value });
      return;
    }
    if (field === "filename") {
      updateCategoryRuleFormRow(rowId, { filenameKeywords: value });
      return;
    }
    updateCategoryRuleFormRow(rowId, { bodyKeywords: value });
  };

  const addTagCategoryRuleFormRow = () => {
    updateRulesForm((prev) => ({
      ...prev,
      tagCategoryRules: [...prev.tagCategoryRules, emptyTagCategoryRuleForm()],
    }));
  };

  const removeTagCategoryRuleFormRow = (rowId: string) => {
    updateRulesForm((prev) => ({
      ...prev,
      tagCategoryRules: prev.tagCategoryRules.filter((row) => row.id !== rowId),
    }));
  };

  const updateTagCategoryRuleFormRow = (rowId: string, patch: Partial<TagCategoryRuleForm>) => {
    updateRulesForm((prev) => ({
      ...prev,
      tagCategoryRules: prev.tagCategoryRules.map((row) => (row.id === rowId ? { ...row, ...patch } : row)),
    }));
  };

  return (
    <section className="space-y-4">
      <article className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="inline-flex items-center gap-1 text-sm text-stone-700">
            <ShieldCheck className="h-4 w-4 text-accent" />
            현재 권한: <span className="font-semibold">{userRole ? userRoleLabel(userRole) : "확인중"}</span>
          </p>
          <button
            className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
            onClick={() => void loadRulesets()}
            disabled={loadingRulesets}
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            새로고침
          </button>
        </div>
        {message ? <p className="mt-2 text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
      </article>

      <div className="grid gap-4 xl:grid-cols-3">
        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel xl:col-span-1">
          <h2 className="mb-3 inline-flex items-center gap-1 text-sm font-semibold">
            <ListFilter className="h-4 w-4 text-accent" />
            규칙셋 목록
          </h2>
          {loadingRulesets ? <p className="text-sm text-stone-600">규칙셋 로딩 중...</p> : null}

          {!loadingRulesets ? (
            <ul className="space-y-2 text-sm">
              {rulesets.length === 0 ? <li className="text-stone-600">규칙셋 없음</li> : null}
              {rulesets.map((row) => (
                <li key={row.id}>
                  <button
                    className={`w-full rounded border px-3 py-2 text-left ${
                      row.id === selectedRulesetId ? "border-accent bg-stone-50" : "border-stone-200 hover:bg-stone-50"
                    }`}
                    onClick={() => setSelectedRulesetId(row.id)}
                  >
                    <p className="font-medium text-stone-900">{row.name}</p>
                    <p className="text-xs text-stone-600">
                      활성={row.is_active ? "예" : "아니오"} | 수정={formatDateTime(row.updated_at)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="mt-4 rounded border border-stone-200 p-3">
            <p className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-stone-700">
              <Pencil className="h-3.5 w-3.5" />
              규칙셋 생성 (관리자)
            </p>
            <div className="space-y-2">
              <input
                className="w-full rounded border border-stone-300 px-2 py-1 text-sm"
                placeholder="규칙셋 이름"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
              />
              <input
                className="w-full rounded border border-stone-300 px-2 py-1 text-sm"
                placeholder="설명"
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
              />
              <button
                className="w-full rounded bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
                onClick={() => void createRuleset()}
                disabled={!isAdmin || busyAction === "create-ruleset"}
              >
                생성
              </button>
            </div>
          </div>
        </article>

        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel xl:col-span-2">
          <h2 className="mb-3 inline-flex items-center gap-1 text-sm font-semibold">
            <Files className="h-4 w-4 text-accent" />
            규칙셋 상세 / 버전 관리
          </h2>
          {!selectedRuleset ? <p className="text-sm text-stone-600">선택된 규칙셋이 없습니다.</p> : null}

          {selectedRuleset ? (
            <div className="space-y-3">
              <div className="grid gap-2 md:grid-cols-[1fr_auto_auto]">
                <input
                  className="rounded border border-stone-300 px-2 py-2 text-sm"
                  value={rulesetDescriptionDraft}
                  onChange={(e) => setRulesetDescriptionDraft(e.target.value)}
                  placeholder="규칙셋 설명"
                />
                <label className="flex items-center gap-1 rounded border border-stone-300 px-2 py-2 text-xs text-stone-700">
                  <input
                    type="checkbox"
                    checked={rulesetActiveDraft}
                    onChange={(e) => setRulesetActiveDraft(e.target.checked)}
                  />
                  활성
                </label>
                <button
                  className="rounded border border-stone-300 px-3 py-2 text-sm hover:bg-stone-50 disabled:opacity-50"
                  onClick={() => void updateRulesetMeta()}
                  disabled={!isAdmin || busyAction === "update-ruleset"}
                >
                  메타 저장
                </button>
              </div>

              {loadingRulesetDetail ? <p className="text-sm text-stone-600">상세 로딩 중...</p> : null}

              <div className="overflow-x-auto rounded border border-stone-200">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-stone-200 text-stone-500">
                      <th className="py-2 pl-3">버전</th>
                      <th className="py-2">활성</th>
                      <th className="py-2">배포시각</th>
                      <th className="py-2 pr-3">작업</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.length === 0 ? (
                      <tr>
                        <td className="py-3 pl-3 text-stone-600" colSpan={4}>
                          버전 없음
                        </td>
                      </tr>
                    ) : null}
                    {versions.map((version) => (
                      <tr key={version.id} className="border-b border-stone-100">
                        <td className="py-2 pl-3">v{version.version_no}</td>
                        <td className="py-2">{version.is_active ? "Y" : "N"}</td>
                        <td className="py-2">{formatDateTime(version.published_at)}</td>
                        <td className="py-2 pr-3">
                          <div className="flex gap-1">
                            <button
                              className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
                              onClick={() => setSelectedVersionId(version.id)}
                            >
                              선택
                            </button>
                            <button
                              className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
                              onClick={() => void activateVersion(version.id)}
                              disabled={!isAdmin || version.is_active || busyAction === `activate-${version.id}`}
                            >
                              활성화
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="rounded border border-stone-200 bg-stone-50 p-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="inline-flex items-center gap-1 text-xs font-semibold text-stone-700">
                    <CircleAlert className="h-3.5 w-3.5 text-amber-600" />
                    규칙 충돌 탐지
                  </p>
                  <button
                    className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
                    onClick={() => void detectConflicts()}
                    disabled={!selectedVersionId || busyAction === "detect-conflicts"}
                  >
                    충돌 탐지 실행
                  </button>
                </div>
                {conflictResult ? (
                  <div className="mt-2 space-y-1 text-xs">
                    <p>total_conflicts: {conflictResult.total_conflicts}</p>
                    <div className="max-h-32 overflow-auto rounded border border-stone-200 bg-white p-2">
                      {conflictResult.conflicts.length === 0 ? (
                        <p className="text-stone-600">충돌 없음</p>
                      ) : (
                        <ul className="space-y-1">
                          {conflictResult.conflicts.map((conflict, idx) => (
                            <li key={`${conflict.keyword}-${idx}`}>
                              [{conflict.source_field}] <span className="font-mono">{conflict.keyword}</span> {"=>"}{" "}
                              {conflict.categories.join(", ")}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="rounded border border-stone-200 p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="inline-flex items-center gap-1 text-xs font-semibold text-stone-700">
                    <FileText className="h-3.5 w-3.5 text-accent" />
                    규칙 편집 {selectedVersion ? `(v${selectedVersion.version_no})` : ""}
                  </p>
                  <div className="inline-flex items-center gap-1">
                    <button
                      className={`rounded border px-2 py-1 text-xs ${
                        rulesEditorMode === "form" ? "border-accent bg-accent/10 text-accent" : "border-stone-300 hover:bg-stone-50"
                      }`}
                      onClick={() => setRulesEditorMode("form")}
                    >
                      폼 편집
                    </button>
                    <button
                      className={`rounded border px-2 py-1 text-xs ${
                        rulesEditorMode === "json" ? "border-accent bg-accent/10 text-accent" : "border-stone-300 hover:bg-stone-50"
                      }`}
                      onClick={() => setRulesEditorMode("json")}
                    >
                      <Braces className="mr-1 inline-block h-3.5 w-3.5" />
                      JSON 고급 편집
                    </button>
                    <button
                      className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
                      onClick={resetRulesTemplate}
                    >
                      기본 템플릿
                    </button>
                  </div>
                </div>
                {loadingVersionDetail ? <p className="mb-2 text-sm text-stone-600">버전 로딩 중...</p> : null}
                {versionDetail ? (
                  <p className="mb-2 text-xs text-stone-600">
                    체크섬={versionDetail.checksum_sha256} | 배포시각={formatDateTime(versionDetail.published_at)}
                  </p>
                ) : null}

                {rulesEditorMode === "form" ? (
                  <div className="space-y-3">
                    <div className="grid gap-2 rounded border border-stone-200 bg-stone-50 p-2 md:grid-cols-[220px_1fr]">
                      <p className="text-xs font-semibold text-stone-700">기본 카테고리</p>
                      <input
                        className="rounded border border-stone-300 bg-white px-2 py-1 text-sm"
                        value={rulesForm.defaultCategory}
                        onChange={(e) =>
                          updateRulesForm((prev) => ({
                            ...prev,
                            defaultCategory: e.target.value,
                          }))
                        }
                        placeholder="기타"
                      />
                    </div>

                    <div className="rounded border border-stone-200 bg-stone-50 p-2">
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-xs font-semibold text-stone-700">카테고리 규칙</p>
                        <button
                          className="inline-flex items-center gap-1 rounded border border-stone-300 bg-white px-2 py-1 text-xs hover:bg-stone-100"
                          onClick={addCategoryRuleFormRow}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          규칙 추가
                        </button>
                      </div>
                      {rulesForm.categoryRules.length === 0 ? <p className="text-xs text-stone-600">카테고리 규칙 없음</p> : null}
                      <div className="space-y-2">
                        {rulesForm.categoryRules.map((row, idx) => (
                          <div key={row.id} className="rounded border border-stone-200 bg-white p-2">
                            <div className="mb-2 flex items-center justify-between">
                              <p className="text-xs font-semibold text-stone-700">규칙 #{idx + 1}</p>
                              <button
                                className="inline-flex items-center gap-1 rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                                onClick={() => removeCategoryRuleFormRow(row.id)}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                삭제
                              </button>
                            </div>
                            <div className="grid gap-2 md:grid-cols-2">
                              <input
                                className="rounded border border-stone-300 px-2 py-1 text-sm"
                                value={row.category}
                                onChange={(e) => updateCategoryRuleFormRow(row.id, { category: e.target.value })}
                                placeholder="카테고리명"
                              />
                              <input
                                className="rounded border border-stone-300 px-2 py-1 text-sm"
                                value={row.tags}
                                onChange={(e) => updateCategoryRuleFormRow(row.id, { tags: e.target.value })}
                                placeholder="자동 태그(쉼표/줄바꿈)"
                              />
                              <textarea
                                className="h-20 rounded border border-stone-300 p-2 text-xs"
                                value={row.titleKeywords}
                                onChange={(e) => updateCategoryRuleKeyword(row.id, "title", e.target.value)}
                                placeholder="제목 키워드 (쉼표/줄바꿈)"
                              />
                              <textarea
                                className="h-20 rounded border border-stone-300 p-2 text-xs"
                                value={row.descriptionKeywords}
                                onChange={(e) => updateCategoryRuleKeyword(row.id, "description", e.target.value)}
                                placeholder="설명 키워드 (쉼표/줄바꿈)"
                              />
                              <textarea
                                className="h-20 rounded border border-stone-300 p-2 text-xs"
                                value={row.filenameKeywords}
                                onChange={(e) => updateCategoryRuleKeyword(row.id, "filename", e.target.value)}
                                placeholder="파일명 키워드 (쉼표/줄바꿈)"
                              />
                              <textarea
                                className="h-20 rounded border border-stone-300 p-2 text-xs"
                                value={row.bodyKeywords}
                                onChange={(e) => updateCategoryRuleKeyword(row.id, "body", e.target.value)}
                                placeholder="본문 키워드 (쉼표/줄바꿈)"
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded border border-stone-200 bg-stone-50 p-2">
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-xs font-semibold text-stone-700">태그 기반 카테고리 규칙</p>
                        <button
                          className="inline-flex items-center gap-1 rounded border border-stone-300 bg-white px-2 py-1 text-xs hover:bg-stone-100"
                          onClick={addTagCategoryRuleFormRow}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          규칙 추가
                        </button>
                      </div>
                      {rulesForm.tagCategoryRules.length === 0 ? <p className="text-xs text-stone-600">태그 규칙 없음</p> : null}
                      <div className="space-y-2">
                        {rulesForm.tagCategoryRules.map((row, idx) => (
                          <div key={row.id} className="rounded border border-stone-200 bg-white p-2">
                            <div className="mb-2 flex items-center justify-between">
                              <p className="text-xs font-semibold text-stone-700">태그 규칙 #{idx + 1}</p>
                              <button
                                className="inline-flex items-center gap-1 rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                                onClick={() => removeTagCategoryRuleFormRow(row.id)}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                                삭제
                              </button>
                            </div>
                            <div className="grid gap-2 md:grid-cols-[1fr_140px]">
                              <input
                                className="rounded border border-stone-300 px-2 py-1 text-sm"
                                value={row.category}
                                onChange={(e) => updateTagCategoryRuleFormRow(row.id, { category: e.target.value })}
                                placeholder="카테고리명"
                              />
                              <select
                                className="rounded border border-stone-300 px-2 py-1 text-sm"
                                value={row.match}
                                onChange={(e) =>
                                  updateTagCategoryRuleFormRow(row.id, {
                                    match: e.target.value === "all" ? "all" : "any",
                                  })
                                }
                              >
                                <option value="any">매칭: any</option>
                                <option value="all">매칭: all</option>
                              </select>
                            </div>
                            <textarea
                              className="mt-2 h-20 w-full rounded border border-stone-300 p-2 text-xs"
                              value={row.tags}
                              onChange={(e) => updateTagCategoryRuleFormRow(row.id, { tags: e.target.value })}
                              placeholder="태그 패턴(쉼표/줄바꿈, * 와일드카드 지원)"
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-stone-600">
                      고급 모드에서는 JSON을 직접 편집할 수 있습니다. 수정 후 아래의 JSON 반영 버튼으로 동기화하세요.
                    </p>
                    <textarea
                      className="h-64 w-full rounded border border-stone-300 p-2 font-mono text-xs"
                      value={rulesJsonText}
                      onChange={(e) => setRulesJsonText(e.target.value)}
                    />
                    <div className="flex justify-end">
                      <button
                        className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
                        onClick={applyJsonToForm}
                      >
                        JSON을 폼에 반영
                      </button>
                    </div>
                  </div>
                )}
                <div className="mt-2 flex justify-end">
                  <button
                    className="rounded bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
                    onClick={() => void createRuleVersion()}
                    disabled={!isAdmin || !selectedRulesetId || busyAction === "create-version"}
                  >
                    새 버전 생성
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </article>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
          <h2 className="mb-3 inline-flex items-center gap-1 text-sm font-semibold">
            <Search className="h-4 w-4 text-accent" />
            패턴 테스트
          </h2>
          <div className="grid gap-2">
            <input
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              placeholder="파일명"
              value={testInput.filename}
              onChange={(e) => setTestInput((prev) => ({ ...prev, filename: e.target.value }))}
            />
            <input
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              placeholder="제목(선택)"
              value={testInput.title}
              onChange={(e) => setTestInput((prev) => ({ ...prev, title: e.target.value }))}
            />
            <textarea
              className="h-24 rounded border border-stone-300 p-2 text-xs"
              placeholder="캡션"
              value={testInput.caption}
              onChange={(e) => setTestInput((prev) => ({ ...prev, caption: e.target.value }))}
            />
            <textarea
              className="h-20 rounded border border-stone-300 p-2 text-xs"
              placeholder="설명(선택)"
              value={testInput.description}
              onChange={(e) => setTestInput((prev) => ({ ...prev, description: e.target.value }))}
            />
            <textarea
              className="h-20 rounded border border-stone-300 p-2 text-xs"
              placeholder="본문 추출 텍스트(선택)"
              value={testInput.body_text}
              onChange={(e) => setTestInput((prev) => ({ ...prev, body_text: e.target.value }))}
            />
            <button
              className="rounded bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
              onClick={() => void executeRuleTest()}
              disabled={!selectedVersionId || busyAction === "rule-test"}
            >
              테스트 실행
            </button>
          </div>
          {testResult ? (
            <div className="mt-3 rounded border border-stone-200 bg-stone-50 p-2 text-xs">
              <p>분류: {testResult.category}</p>
              <p>태그: {testResult.tags.join(", ") || "-"}</p>
              <p>문서시점: {testResult.event_date ?? "-"}</p>
              <p>검토필요: {testResult.review_needed ? "예" : "아니오"}</p>
            </div>
          ) : null}
        </article>

        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
          <h2 className="mb-3 inline-flex items-center gap-1 text-sm font-semibold">
            <History className="h-4 w-4 text-accent" />
            기존 데이터 재처리 (Backfill)
          </h2>
          <div className="grid gap-2 md:grid-cols-2">
            <input
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              placeholder="배치 크기(batch_size)"
              value={backfillBatchSize}
              onChange={(e) => setBackfillBatchSize(e.target.value)}
            />
            <input
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              placeholder="카테고리 ID(선택)"
              value={backfillCategoryId}
              onChange={(e) => setBackfillCategoryId(e.target.value)}
            />
            <input
              type="date"
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              value={backfillFrom}
              onChange={(e) => setBackfillFrom(e.target.value)}
            />
            <input
              type="date"
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              value={backfillTo}
              onChange={(e) => setBackfillTo(e.target.value)}
            />
          </div>
          <label className="mt-2 flex items-center gap-1 text-sm text-stone-700">
            <input
              type="checkbox"
              checked={backfillReviewOnly}
              onChange={(e) => setBackfillReviewOnly(e.target.checked)}
            />
            검토 필요 문서만
          </label>
          <button
            className="mt-2 rounded border border-stone-300 px-3 py-1 text-sm hover:bg-stone-50 disabled:opacity-50"
            onClick={() => void triggerBackfill()}
            disabled={!isAdmin || !selectedVersionId || busyAction === "backfill"}
          >
            재처리 실행
          </button>

          <div className="mt-3 rounded border border-stone-200 bg-stone-50 p-2">
            <p className="mb-1 text-xs font-semibold text-stone-700">배치 시뮬레이션 비교</p>
            <div className="flex flex-wrap items-center gap-2">
              <input
                className="rounded border border-stone-300 px-2 py-1 text-sm"
                placeholder="샘플 제한(limit)"
                value={simulationLimit}
                onChange={(e) => setSimulationLimit(e.target.value)}
              />
              <button
                className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
                onClick={() => void runBatchSimulation()}
                disabled={!selectedVersionId || busyAction === "simulate-batch"}
              >
                시뮬레이션 실행
              </button>
            </div>
            {simulationResult ? (
              <div className="mt-2 text-xs">
                <p>
                  스캔={simulationResult.scanned}, 변경={simulationResult.changed}, 미변경={simulationResult.unchanged}
                </p>
                <div className="mt-1 max-h-40 overflow-auto rounded border border-stone-200 bg-white">
                  <table className="w-full text-left text-[11px]">
                    <thead className="border-b border-stone-200 text-stone-500">
                      <tr>
                        <th className="px-2 py-1">문서</th>
                        <th className="px-2 py-1">카테고리</th>
                        <th className="px-2 py-1">변경필드</th>
                      </tr>
                    </thead>
                    <tbody>
                      {simulationResult.samples.slice(0, 50).map((sample) => (
                        <tr key={sample.document_id} className="border-b border-stone-100">
                          <td className="px-2 py-1">{sample.title}</td>
                          <td className="px-2 py-1">
                            {sample.current_category ?? "-"} {"->"} {sample.predicted_category}
                          </td>
                          <td className="px-2 py-1">{sample.changed_fields.join(", ") || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>

          {lastBackfillJob ? (
            <div className="mt-3 rounded border border-stone-200 bg-stone-50 p-2 text-xs">
              <p>작업 ID: {lastBackfillJob.job_id}</p>
              <p>상태: {lastBackfillJob.status}</p>
            </div>
          ) : null}
        </article>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="inline-flex items-center gap-1 text-sm font-semibold">
              <FileText className="h-4 w-4 text-accent" />
              규칙 JSON 내보내기
            </h2>
            <button
              className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
              onClick={() => void exportRuleset()}
              disabled={!selectedRulesetId || busyAction === "export-ruleset"}
            >
              내보내기 실행
            </button>
          </div>
          <textarea
            className="h-64 w-full rounded border border-stone-300 p-2 font-mono text-xs"
            value={exportText}
            onChange={(e) => setExportText(e.target.value)}
            placeholder="규칙셋 내보내기 결과가 여기에 표시됩니다."
          />
        </article>

        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
          <h2 className="mb-2 inline-flex items-center gap-1 text-sm font-semibold">
            <FileText className="h-4 w-4 text-accent" />
            규칙 JSON 가져오기 (관리자)
          </h2>
          <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
            <input
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              placeholder="새 규칙셋 이름"
              value={importName}
              onChange={(e) => setImportName(e.target.value)}
            />
            <input
              className="rounded border border-stone-300 px-2 py-1 text-sm"
              placeholder="설명(선택)"
              value={importDescription}
              onChange={(e) => setImportDescription(e.target.value)}
            />
            <label className="flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs text-stone-700">
              <input
                type="checkbox"
                checked={importActivateLatest}
                onChange={(e) => setImportActivateLatest(e.target.checked)}
              />
              최신 버전 즉시 활성화
            </label>
          </div>
          <textarea
            className="mt-2 h-52 w-full rounded border border-stone-300 p-2 font-mono text-xs"
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder='배열 또는 {"versions":[...]} 형태의 JSON'
          />
          <button
            className="mt-2 rounded bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
            onClick={() => void importRules()}
            disabled={!isAdmin || busyAction === "import-ruleset"}
          >
            가져오기 실행
          </button>
        </article>
      </div>
    </section>
  );
}
