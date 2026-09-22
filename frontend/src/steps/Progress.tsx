export default function Progress({ messages, title }: { messages: string[]; title: string }) {
  return (
    <div className="progress">
      <div className="spinner" />
      <div>
        <div className="progress-title">{title}</div>
        <ul className="log">
          {messages.map((m, i) => <li key={i} className={i === messages.length - 1 ? 'current' : ''}>{m}</li>)}
        </ul>
      </div>
    </div>
  )
}
