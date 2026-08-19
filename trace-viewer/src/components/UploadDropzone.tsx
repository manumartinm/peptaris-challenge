import { useRef, useState, type DragEvent, type ChangeEvent } from "react";

interface UploadDropzoneProps {
  onFile: (file: File) => void;
  busy: boolean;
}

export function UploadDropzone({ onFile, busy }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function takeFile(file: File | undefined) {
    if (file) onFile(file);
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setOver(false);
    takeFile(event.dataTransfer.files[0]);
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    takeFile(event.target.files?.[0]);
    event.target.value = "";
  }

  return (
    <section
      className={over ? "dropzone over" : "dropzone"}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <p className="dropzone-kicker">Open a pipeline trace</p>
      <h2>Drop a .trace.json file</h2>
      <p className="dropzone-copy">
        The file stays in this browser. Nothing is uploaded or stored.
      </p>
      <button
        type="button"
        className="primary-button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? "Reading file…" : "Choose file"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={onChange}
      />
    </section>
  );
}
