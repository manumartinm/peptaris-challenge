import { useEffect, useRef } from "react";

export function MoleculeViewer({ cif }: { cif: string }) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !cif.trim()) return;

    let cancelled = false;
    let resize: (() => void) | undefined;
    let observer: ResizeObserver | undefined;

    void import("3dmol").then((Mol3D) => {
      if (cancelled || hostRef.current !== host) return;
      const viewer = Mol3D.createViewer(host, {
        backgroundColor: "#ffffff",
        cartoonQuality: 10,
      });
      viewer.addModel(cif, "cif");
      viewer.setStyle(
        {},
        {
          cartoon: { color: "spectrum", thickness: 0.4 },
          stick: { radius: 0.14, colorscheme: "Jmol" },
        },
      );
      viewer.zoomTo();
      viewer.render();
      resize = () => viewer.resize();
      observer = new ResizeObserver(resize);
      observer.observe(host);
      window.addEventListener("resize", resize);
    });

    return () => {
      cancelled = true;
      if (resize) window.removeEventListener("resize", resize);
      observer?.disconnect();
      host.replaceChildren();
    };
  }, [cif]);

  return (
    <div className="molecule-viewer-frame">
      <div
        ref={hostRef}
        className="molecule-viewer"
        role="img"
        aria-label="Predicted 3D structure"
      />
      <p className="molecule-viewer-hint">Drag to rotate · scroll to zoom</p>
    </div>
  );
}
