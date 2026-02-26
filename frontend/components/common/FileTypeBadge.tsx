import { FileArchive, FileCode2, FileImage, FileSpreadsheet, FileText, Presentation } from "lucide-react";

export type FileTypeKind = "pdf" | "spreadsheet" | "document" | "image" | "presentation" | "archive" | "text" | "other";

const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff", "svg", "heic"]);
const SPREADSHEET_EXTENSIONS = new Set(["xls", "xlsx", "csv", "ods"]);
const DOCUMENT_EXTENSIONS = new Set(["doc", "docx", "hwp", "hwpx", "odt", "rtf"]);
const PRESENTATION_EXTENSIONS = new Set(["ppt", "pptx", "odp", "key"]);
const ARCHIVE_EXTENSIONS = new Set(["zip", "7z", "rar", "tar", "gz", "bz2", "xz"]);
const TEXT_EXTENSIONS = new Set(["txt", "md", "log", "json", "xml", "yml", "yaml"]);

function extensionOf(filename: string): string {
  const normalized = filename.trim().toLowerCase();
  const dotIdx = normalized.lastIndexOf(".");
  if (dotIdx < 0 || dotIdx >= normalized.length - 1) return "";
  return normalized.slice(dotIdx + 1);
}

export function detectFileType(filename: string, mimeType?: string): FileTypeKind {
  const ext = extensionOf(filename);
  const mime = (mimeType || "").toLowerCase();
  if (ext === "pdf" || mime.includes("pdf")) return "pdf";
  if (SPREADSHEET_EXTENSIONS.has(ext) || mime.includes("spreadsheet") || mime.includes("excel") || mime.includes("csv")) return "spreadsheet";
  if (DOCUMENT_EXTENSIONS.has(ext) || mime.includes("word") || mime.includes("officedocument.wordprocessingml")) return "document";
  if (IMAGE_EXTENSIONS.has(ext) || mime.startsWith("image/")) return "image";
  if (PRESENTATION_EXTENSIONS.has(ext) || mime.includes("presentation") || mime.includes("powerpoint")) return "presentation";
  if (ARCHIVE_EXTENSIONS.has(ext) || mime.includes("zip") || mime.includes("compressed")) return "archive";
  if (TEXT_EXTENSIONS.has(ext) || mime.startsWith("text/")) return "text";
  return "other";
}

function extensionLabel(filename: string): string {
  const ext = extensionOf(filename);
  return ext ? ext.toUpperCase() : "FILE";
}

function iconFor(kind: FileTypeKind) {
  if (kind === "pdf") return <FileText className="h-3.5 w-3.5" />;
  if (kind === "spreadsheet") return <FileSpreadsheet className="h-3.5 w-3.5" />;
  if (kind === "document") return <FileText className="h-3.5 w-3.5" />;
  if (kind === "image") return <FileImage className="h-3.5 w-3.5" />;
  if (kind === "presentation") return <Presentation className="h-3.5 w-3.5" />;
  if (kind === "archive") return <FileArchive className="h-3.5 w-3.5" />;
  if (kind === "text") return <FileCode2 className="h-3.5 w-3.5" />;
  return <FileText className="h-3.5 w-3.5" />;
}

function classFor(kind: FileTypeKind): string {
  if (kind === "pdf") return "border-red-200 bg-red-50 text-red-700";
  if (kind === "spreadsheet") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (kind === "document") return "border-blue-200 bg-blue-50 text-blue-700";
  if (kind === "image") return "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700";
  if (kind === "presentation") return "border-amber-200 bg-amber-50 text-amber-700";
  if (kind === "archive") return "border-violet-200 bg-violet-50 text-violet-700";
  if (kind === "text") return "border-slate-300 bg-slate-100 text-slate-700";
  return "border-stone-300 bg-stone-100 text-stone-700";
}

type FileTypeBadgeProps = {
  filename: string;
  mimeType?: string;
  compact?: boolean;
};

export function FileTypeBadge({ filename, mimeType, compact = false }: FileTypeBadgeProps) {
  const kind = detectFileType(filename, mimeType);
  const label = extensionLabel(filename);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-semibold leading-none ${classFor(kind)} ${
        compact ? "text-[10px]" : "text-[11px]"
      }`}
      title={filename}
    >
      {iconFor(kind)}
      {label}
    </span>
  );
}
