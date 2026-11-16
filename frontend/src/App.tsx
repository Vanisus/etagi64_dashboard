import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ApiError, request, write } from './api'
import type { Category, City, Daily, Dashboard, Phrase, Run, Topic } from './api'

const number = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить запрос'
const dateText = (value: string) => new Date(value).toLocaleString('ru-RU')
const idField = { pattern: '[a-z0-9][a-z0-9_-]*', maxLength: 128 }

function Modal({ title, close, children }: {title: string; close: () => void; children: ReactNode}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const root = ref.current
    root?.querySelector<HTMLElement>('button,input,select')?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
      if (event.key !== 'Tab' || !root) return
      const nodes = [...root.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]')]
      const first = nodes[0], last = nodes.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); previous?.focus() }
  }, [close])
  return <div className="overlay"><div className="modal" ref={ref} role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="panel-head"><h2 id="modal-title">{title}</h2><button onClick={close} aria-label="Закрыть">×</button></div>{children}</div></div>
}

function Login({close, success}: {close: () => void; success: () => void}) {
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    try {
      await request('/auth/login', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body: new URLSearchParams({username: String(form.get('email')), password: String(form.get('password'))})})
      await request('/auth/me'); success()
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  return <Modal title="Вход для команды" close={close}><p className="muted">Управление каталогом и сбором статистики.</p><form onSubmit={submit}><label>Email<input type="email" name="email" autoComplete="username" required /></label><label>Пароль<input name="password" type="password" autoComplete="current-password" required /></label>{error && <div className="error" role="alert">{error}</div>}<button className="primary full" disabled={busy}>{busy?'Входим…':'Войти в панель'}</button></form></Modal>
}

function TopicCard({topic, index, daily}: {topic: Topic; index: number; daily: boolean}) {
  const [expanded, setExpanded] = useState(false)
  const value = daily ? topic.current_total : topic.average_frequency
  const positive = topic.trend === 'up', negative = topic.trend === 'down'
  const trend = topic.trend === 'flat' ? 'Без изменений' : topic.trend === 'no_data' || !topic.trend ? 'Нет сравнения' : `${positive?'↑':negative?'↓':''} ${topic.delta_percent == null ? 'Процент не определён' : `${number(Math.abs(topic.delta_percent))}%`}`
  return <article className={`topic accent-${index % 5}`}><div className="topic-row"><span className="topic-symbol" aria-hidden="true">{['⌂','▥','◇','↗','%'][index%5]}</span><div className="topic-title"><span className="caption">ТЕМА {String(index+1).padStart(2,'0')}</span><h3>{topic.category_name}</h3><p className="muted">{daily?`${topic.compared_queries ?? 0} из ${topic.expected_queries} фраз сопоставлено`:`${topic.successful_queries ?? 0} из ${topic.expected_queries} фраз собрано`}</p></div><div className="metric"><strong>{number(value)}</strong><span>{daily?'сумма частот фраз за день':'средняя частотность фраз'}</span></div><span className={`badge ${daily?(positive?'up':negative?'down':''):topic.complete?'up':''}`}>{daily?trend:topic.complete?'Полный снимок':'Неполные данные'}</span><button className="round" aria-label={`Подробнее: ${topic.category_name}`} aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'−':'+'}</button></div>{expanded && <div className="topic-detail">{daily?<>Предыдущий день: {number(topic.previous_total)}. Абсолютное изменение: {number(topic.delta)}. Сумма может учитывать пересечения поисковых формулировок.</>:<>Среднее по успешно собранным фразам. Показатель не равен числу покупателей или уникальных поисков.</>}{!topic.complete && ' Данные неполные; не интерпретируйте пропуски как нулевой спрос.'}</div>}</article>
}

function Home({cities}: {cities: City[]}) {
  const [city, setCity] = useState(''), [mode,setMode] = useState<'month'|'daily'>('month'), [date,setDate] = useState('')
  const [topics,setTopics] = useState<Topic[]>([]), [loading,setLoading] = useState(false), [error,setError] = useState(''), [note,setNote] = useState(''), [version,setVersion] = useState(0)
  useEffect(()=>{if(!cities.some(c=>c.id===city))setCity(cities[0]?.id || '')},[cities,city])
  useEffect(()=>{
    if(!city)return
    const abort = new AbortController(); setLoading(true); setError(''); setTopics([]); setNote('')
    const params = new URLSearchParams({city_id:city});if(date&&mode==='daily')params.set('metric_date',date)
    async function load(){try {
      if(mode==='month') {
        const result=await request<Dashboard>(`/public/dashboard?${params}`,{signal:abort.signal})
        if(abort.signal.aborted)return
        setTopics(result.items);setNote(!result.has_data?'Общий сбор города ещё не выполнен.':`${result.updated_at?'Обновлено '+dateText(result.updated_at):''}${result.catalog_changed?' · Каталог изменён после сбора.':''}`)
      } else {
        const result=await request<Daily>(`/public/daily?${params}`,{signal:abort.signal})
        if(abort.signal.aborted)return
        setTopics(result.categories);setNote(`${result.current_date} против ${result.previous_date} · ${result.comparison_status==='complete'?'Полные данные':result.comparison_status==='partial'?'Частичные данные':'Нет данных для сравнения'}. ${result.aggregation_note}`)
      }
    }catch(e){if(!abort.signal.aborted)setError(message(e))}finally{if(!abort.signal.aborted)setLoading(false)}}
    void load();return()=>abort.abort()
  },[city,mode,date,version])
  return <><div className="intro"><div><div className="eyebrow">ПУЛЬС РЫНКА НЕДВИЖИМОСТИ</div><h1>Спрос. В деталях.</h1><p className="muted">Темы, которые интересуют людей. Цифры, которые помогают видеть больше.</p></div><label className="city-picker">Ваш город<select value={city} onChange={e=>setCity(e.target.value)} disabled={!cities.length}>{cities.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div><section className="hero"><div><span className="caption">АНАЛИТИКА ПОИСКОВОГО ИНТЕРЕСА</span><h2>Большая картина.<br/>Понятные показатели.</h2><p>От квартир до загородных домов — все направления в одной сводке.</p></div><div className="hero-stat"><strong>{loading?'…':topics.length}</strong><span>тем в выбранном городе</span><small>Источник · Яндекс Wordstat</small></div></section><div className="toolbar"><div><h2>Что происходит на рынке</h2><p className="muted">{mode==='month'?'Частотность за последние 30 дней':'Сравнение завершённых календарных дней'}</p></div><div className="controls"><div className="segments"><button className={mode==='month'?'selected':''} onClick={()=>setMode('month')}>За 30 дней</button><button className={mode==='daily'?'selected':''} onClick={()=>setMode('daily')}>По дням</button></div>{mode==='daily'&&<input aria-label="Дата статистики" type="date" value={date} onChange={e=>setDate(e.target.value)}/>}<button onClick={()=>setVersion(v=>v+1)} aria-label="Обновить данные">↻</button></div></div>{note&&<p className="notice">{note}</p>}{error&&<div className="error" role="alert">{error}<button onClick={()=>setVersion(v=>v+1)}>Повторить</button></div>}{loading?<div className="empty" role="status">Загружаем статистику…</div>:<div className="topics">{topics.map((t,i)=><TopicCard key={t.category_id} topic={t} index={i} daily={mode==='daily'}/>)}{!topics.length&&!error&&<div className="empty">Пока нет данных. Добавьте город и фразы, затем выполните сбор в панели администратора.</div>}</div>}<p className="footnote">Частотность отражает поисковый интерес, а не число сделок или покупателей. Составы тем различаются, а запросы могут пересекаться.</p></>
}

type Section = 'queries' | 'categories' | 'cities' | 'collections'
type RecordValue = Partial<Phrase & City & Category>
function Admin({onChanged}: {onChanged:()=>void}) {
  const [tab,setTab]=useState<Section>('queries'), [cities,setCities]=useState<City[]>([]), [categories,setCategories]=useState<Category[]>([])
  const [phrases,setPhrases]=useState<Phrase[]>([]), [runs,setRuns]=useState<Run[]>([]), [total,setTotal]=useState(0), [page,setPage]=useState(0)
  const [city,setCity]=useState(''), [search,setSearch]=useState(''), [appliedSearch,setAppliedSearch]=useState(''), [error,setError]=useState(''), [loading,setLoading]=useState(false), [revision,setRevision]=useState(0)
  const [editor,setEditor]=useState<{type:Section;record:RecordValue}|null>(null), [saving,setSaving]=useState(false), [formError,setFormError]=useState(''), [method,setMethod]=useState('dynamics'), [info,setInfo]=useState('')
  const closeEditor=useCallback(()=>setEditor(null),[])
  useEffect(()=>{const timeout=setTimeout(()=>{setAppliedSearch(search);setPage(0)},300);return()=>clearTimeout(timeout)},[search])
  useEffect(()=>{const abort=new AbortController();setLoading(true);setError('');const options={signal:abort.signal};async function load(){try {
    const [cs,cat]=await Promise.all([request<City[]>('/cities',options),request<Category[]>('/categories',options)])
    if(abort.signal.aborted)return;setCities(cs);setCategories(cat)
    if(tab==='queries'){const q=new URLSearchParams({limit:'25',offset:String(page*25)});if(city)q.set('city_id',city);if(appliedSearch)q.set('search',appliedSearch);const result=await request<{items:Phrase[];total:number}>(`/queries?${q}`,options);if(!abort.signal.aborted){setPhrases(result.items);setTotal(result.total)}}
    if(tab==='collections'){const q=new URLSearchParams({limit:'30'});if(city)q.set('city_id',city);const result=await request<Run[]>(`/collections?${q}`,options);if(!abort.signal.aborted)setRuns(result)}
  }catch(e){if(!abort.signal.aborted)setError(message(e))}finally{if(!abort.signal.aborted)setLoading(false)}}void load();return()=>abort.abort()},[tab,city,appliedSearch,page,revision])
  useEffect(()=>{if(tab!=='collections')return;const timer=setInterval(()=>setRevision(v=>v+1),10000);return()=>clearInterval(timer)},[tab])
  async function save(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!editor)return;setSaving(true);setFormError('');const form=new FormData(event.currentTarget);const id=String(form.get('id'));let body:object
    if(editor.type==='queries')body={phrase:String(form.get('phrase')).trim(),category_id:String(form.get('category_id')),city_id:form.get('city_id')||null,enabled:form.has('enabled')}
    else if(editor.type==='cities')body={name:String(form.get('name')).trim(),yandex_region_id:form.get('yandex_region_id')||null}
    else body={name:String(form.get('name')).trim()}
    try{await write(`/${editor.type}${editor.record.id?'/'+encodeURIComponent(id):''}`,editor.record.id?'PATCH':'POST',editor.record.id?body:{id,...body});setEditor(null);setRevision(v=>v+1);onChanged()}catch(e){setFormError(message(e))}finally{setSaving(false)}
  }
  async function collect(){if(!city){setError('Сначала выберите город.');return}if(!window.confirm('Запустить сбор? Запросы Wordstat могут тарифицироваться.'))return;setSaving(true);setError('');setInfo('');try{await write('/collections','POST',{city_id:city,method});setInfo('Задание создано. Статус обновляется каждые 10 секунд.');setRevision(v=>v+1)}catch(e){setError(message(e))}finally{setSaving(false)}}
  const edit=(type:Section,record:RecordValue={})=>{setFormError('');setEditor({type,record})}
  return <><div className="eyebrow">ПАНЕЛЬ УПРАВЛЕНИЯ</div><h1>Всё под контролем.</h1><p className="muted">Настройки каталога и сбор статистики — без редактирования JSON.</p><div className="admin-layout"><nav className="side">{([['queries','Поисковые фразы'],['categories','Темы'],['cities','Города'],['collections','Сбор статистики']] as const).map(([id,label])=><button className={tab===id?'active':''} key={id} onClick={()=>{setTab(id);setPage(0);setError('')}}>{label}</button>)}</nav><section className="panel"><div className="panel-head"><h2>{({queries:'Поисковые фразы',categories:'Темы',cities:'Города и регионы',collections:'История сборов'})[tab]}</h2>{tab!=='collections'&&<button className="primary" onClick={()=>edit(tab)}>+ Добавить</button>}</div>{(tab==='queries'||tab==='collections')&&<div className="controls filter"><select aria-label="Город" value={city} onChange={e=>{setCity(e.target.value);setPage(0)}}><option value="">Все города</option>{cities.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>{tab==='queries'?<input aria-label="Поиск фразы" placeholder="Найти фразу…" value={search} onChange={e=>setSearch(e.target.value)}/>:<><select aria-label="Метод сбора" value={method} onChange={e=>setMethod(e.target.value)}><option value="dynamics">Дневная статистика</option><option value="topRequests">Частотность за 30 дней</option></select><button className="primary" disabled={saving||!city} onClick={()=>void collect()}>Запустить сбор</button></>}</div>}{error&&<div className="error" role="alert">{error}</div>}{info&&<div className="notice" role="status">{info}</div>}{loading?<p role="status">Загружаем…</p>:<div className="table-wrap"><table><thead><tr>{(tab==='queries'?['Фраза','Город / тема','Статус','']:tab==='cities'?['Город','Регион Wordstat','']:tab==='categories'?['Название','ID','']:['Дата','Метод','Состояние','Ошибка']).map((h,i)=><th key={i}>{h}</th>)}</tr></thead><tbody>{tab==='queries'&&phrases.map(p=><tr key={p.id}><td>{p.phrase}<small>{p.id}</small></td><td>{cities.find(c=>c.id===p.city_id)?.name||'Без города'}<small>{categories.find(c=>c.id===p.category_id)?.name||p.category_id}</small></td><td><span className={`badge ${p.enabled?'up':''}`}>{p.enabled?'Включена':'Выключена'}</span></td><td><button onClick={()=>edit('queries',p)}>Изменить</button></td></tr>)}{tab==='categories'&&categories.map(c=><tr key={c.id}><td>{c.name}</td><td>{c.id}</td><td><button onClick={()=>edit('categories',c)}>Изменить</button></td></tr>)}{tab==='cities'&&cities.map(c=><tr key={c.id}><td>{c.name}<small>{c.id}</small></td><td>{c.yandex_region_id||'Не задан'}</td><td><button onClick={()=>edit('cities',c)}>Изменить</button></td></tr>)}{tab==='collections'&&runs.map(r=><tr key={r.id}><td>{dateText(r.started_at)}<small>{r.id.slice(0,8)}</small></td><td>{r.method}</td><td><span className="badge">{r.status}</span></td><td>{r.error||'—'}</td></tr>)}</tbody></table>{((tab==='queries'&&!phrases.length)||(tab==='collections'&&!runs.length))&&<p className="empty">Ничего не найдено.</p>}</div>}{tab==='queries'&&<div className="pagination"><button disabled={page===0||loading} onClick={()=>setPage(p=>p-1)}>Назад</button><span>{total?`${page*25+1}–${Math.min((page+1)*25,total)} из ${total}`:'0 записей'}</span><button disabled={(page+1)*25>=total||loading} onClick={()=>setPage(p=>p+1)}>Далее</button></div>}</section></div>{editor&&<Modal title={editor.record.id?'Редактирование':'Новая запись'} close={closeEditor}><form onSubmit={save}><label>Идентификатор<input name="id" defaultValue={editor.record.id||''} readOnly={!!editor.record.id} required {...idField}/></label>{editor.type==='queries'?<><label>Фраза<input name="phrase" defaultValue={editor.record.phrase||''} required maxLength={400}/></label><label>Город<select name="city_id" defaultValue={editor.record.city_id||''}><option value="">Без города</option>{cities.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Тема<select name="category_id" defaultValue={editor.record.category_id||categories[0]?.id||''} required><option value="" disabled>Выберите тему</option>{categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label className="checkbox"><input type="checkbox" name="enabled" defaultChecked={editor.record.enabled!==false}/>Включена в сбор</label></>:<><label>Название<input name="name" defaultValue={editor.record.name||''} required maxLength={200}/></label>{editor.type==='cities'&&<label>ID региона Wordstat<input name="yandex_region_id" defaultValue={editor.record.yandex_region_id||''} pattern="[1-9][0-9]{0,18}" inputMode="numeric"/><small>Пустое значение отключает регион. Сбор без региона не выполняется.</small></label>}</>}{formError&&<div className="error" role="alert">{formError}</div>}<div className="actions"><button type="button" onClick={closeEditor} disabled={saving}>Отмена</button><button className="primary" disabled={saving}>{saving?'Сохраняем…':'Сохранить'}</button></div></form></Modal>}</>
}

export default function App(){
  const [cities,setCities]=useState<City[]>([]),[user,setUser]=useState(false),[checking,setChecking]=useState(true),[login,setLogin]=useState(false),[admin,setAdmin]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0)
  const closeLogin=useCallback(()=>setLogin(false),[])
  useEffect(()=>{const abort=new AbortController();void request<City[]>('/public/cities',{signal:abort.signal}).then(setCities).catch(e=>{if(!abort.signal.aborted)setError(message(e))});return()=>abort.abort()},[revision])
  useEffect(()=>{void request('/auth/me').then(()=>setUser(true)).catch(e=>{if(!(e instanceof ApiError)||![401,403].includes(e.status))setError(message(e))}).finally(()=>setChecking(false));const expire=()=>{setUser(false);setAdmin(false)};window.addEventListener('session-expired',expire);return()=>window.removeEventListener('session-expired',expire)},[])
  async function logout(){try{await request('/auth/logout',{method:'POST'});setUser(false);setAdmin(false)}catch(e){setError(message(e))}}
  return <><header><a className="brand" href="#" onClick={e=>{e.preventDefault();setAdmin(false)}}><span className="logo">этажи</span><span className="brand-label">Аналитика недвижимости</span></a><div className="controls">{admin&&<button onClick={()=>setAdmin(false)}>На главную</button>}<button className="primary" disabled={checking} onClick={()=>user?setAdmin(true):setLogin(true)}>{checking?'…':user?'Админ-панель':'Войти ↗'}</button>{user&&<button onClick={()=>void logout()}>Выйти</button>}</div></header><main>{error&&<div className="error" role="alert">{error}<button onClick={()=>{setError('');setRevision(v=>v+1)}}>Повторить</button></div>}{admin&&user?<Admin onChanged={()=>setRevision(v=>v+1)}/>:<Home cities={cities}/>}</main><footer><span>Этажи · Пульс спроса</span><span>Поисковый интерес, а не прогноз сделок</span></footer>{login&&<Login close={closeLogin} success={()=>{setUser(true);setLogin(false);setAdmin(true)}}/>}</>
}
