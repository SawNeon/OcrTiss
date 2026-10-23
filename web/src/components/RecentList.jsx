export default function RecentList({ items, currentId, onOpen }) {
  if (!items?.length) return null

  return (
    <section className="recentes">
      <h2>Guias desta sessão</h2>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" aria-current={item.id === currentId} onClick={() => onOpen(item.id)}>
              <span className="recentes__nome">{item.original_name}</span>
              <span className="recentes__situacao">
                {item.fields_to_review > 0
                  ? `${item.fields_to_review} a conferir`
                  : `${item.fields_read} campos conferidos`}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
