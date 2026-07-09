export default function ResultCard({ message, result, error }) {
    return (
      <div className="rounded-lg border border-white/10 bg-[#1C1F26] p-4">
        <p className="mb-3 text-sm text-[#E8E6E1]">{message}</p>
  
        {error && <p className="text-sm text-[#E07A5F]">Failed: {error}</p>}
  
        {result && (
          <>
            <p className="mb-2 text-xs uppercase tracking-wide text-[#8B8F98]">
              {result.domain}
            </p>
            <ul className="flex flex-col gap-1.5">
              {result.written.map((w) => (
                <li key={w.concept_id} className="flex items-center gap-2 text-xs font-mono">
                  <span
                    className={
                      "rounded px-1.5 py-0.5 " +
                      (w.action === "created"
                        ? "bg-[#4FB6A8]/20 text-[#4FB6A8]"
                        : "bg-[#D4A64A]/20 text-[#D4A64A]")
                    }
                  >
                    {w.action}
                  </span>
                  <span className="text-[#E8E6E1]">{w.concept_id}</span>
                  <span className="text-[#5B5F68]">({w.type})</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    );
  }