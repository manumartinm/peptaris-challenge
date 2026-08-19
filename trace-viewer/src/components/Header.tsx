import { useState } from "react";

interface HeaderProps {
  fileName: string | null;
  linkHref: string | null;
  onHome: () => void;
  onNewRequest: () => void;
}

export function Header({ fileName, linkHref, onHome, onNewRequest }: HeaderProps) {
  const [copied, setCopied] = useState(false);

  async function copyLink() {
    if (!linkHref) return;
    const url = new URL(linkHref, window.location.origin).toString();
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      window.prompt("Copy this trace URL", url);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <header className="app-header">
      <button type="button" className="brand brand-button" onClick={onHome}>
        <img
          className="penn-shield"
          src="/penn-shield.svg"
          alt="University of Pennsylvania shield"
        />
        <div className="brand-copy">
          <p className="eyebrow">University of Pennsylvania</p>
          <h1>Trace Explorer</h1>
          <p className="subtitle">De la Fuente Lab</p>
        </div>
      </button>
      {fileName ? (
        <div className="header-file">
          <span className="file-name">{fileName}</span>
          {linkHref ? (
            <button type="button" className="ghost-button" onClick={() => void copyLink()}>
              {copied ? "Copied" : "Copy link"}
            </button>
          ) : null}
          <button type="button" className="ghost-button" onClick={onNewRequest}>
            New request
          </button>
        </div>
      ) : null}
    </header>
  );
}
