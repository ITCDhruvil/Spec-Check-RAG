"use client";

import { useCallback, useState } from "react";

const ACCEPTED = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
    ".docx",
  ],
};

export function UploadDropzone({
  onFileSelected,
  disabled,
}: {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}) {
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validate = useCallback((file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["pdf", "docx"].includes(ext)) {
      return "Only PDF and DOCX files are supported.";
    }
    const maxMb = 50;
    if (file.size > maxMb * 1024 * 1024) {
      return `File must be under ${maxMb} MB.`;
    }
    return null;
  }, []);

  const handleFile = useCallback(
    (file: File) => {
      const validationError = validate(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      setError(null);
      onFileSelected(file);
    },
    [onFileSelected, validate]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [disabled, handleFile]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={onDrop}
      className={`rounded-lg border-2 border-dashed p-10 text-center transition ${
        dragActive
          ? "border-accent bg-blue-50/40"
          : "border-surface-border bg-surface"
      } ${disabled ? "opacity-60" : ""}`}
    >
      <p className="text-sm font-medium text-ink">Drag and drop a document</p>
      <p className="mt-1 text-xs text-ink-muted">PDF or DOCX, up to 50 MB</p>
      <label className="mt-4 inline-block cursor-pointer rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover">
        Browse files
        <input
          type="file"
          className="hidden"
          accept={Object.values(ACCEPTED).flat().join(",")}
          disabled={disabled}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </label>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  );
}
