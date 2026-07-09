export default function OwnerBar({ owner, onChange }) {
    return (
      <div className="mt-2 flex items-center gap-2 text-sm text-[#8B8F98]">
        <span>Dashboard for</span>
        <input
          value={owner}
          onChange={(e) => onChange(e.target.value)}
          className="w-32 border-b border-white/20 bg-transparent px-1 py-0.5 font-mono text-[#E8E6E1] outline-none focus:border-[#D4A64A]"
        />
      </div>
    );
  }