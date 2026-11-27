/**
 * The six languages the landing demonstrates, and the passage it demonstrates
 * them with.
 *
 * WHY THIS IS A MODULE AND NOT JSX
 * --------------------------------
 * The rotation needs the same list in three places (the hero pane, the
 * demonstration section, and the language rail), and the tests need to assert
 * that every entry is well-formed without rendering React. Keeping the data in
 * one typed module means a seventh language is one array entry, not a hunt
 * through components.
 *
 * THE PASSAGE
 * -----------
 * One editorial sentence from a travel memoir, translated into all six. The
 * translations are real translations of the same sentence, not transliterations
 * of the English word order: each was written to sound like a sentence a
 * translator would actually produce, because a demonstration of translation
 * quality that reads like machine output argues against the product.
 *
 * `dir` is per-language and is the single source of truth for text direction.
 * Persian and Arabic are RTL; the other four are LTR. The component reads this
 * field rather than testing for a language code, so adding Hebrew or Urdu later
 * cannot forget to set direction.
 */

export type DemoLangCode = 'en' | 'fa' | 'ar' | 'es' | 'fr' | 'de'

export interface DemoLanguage {
  /** BCP-47 tag for the `lang` attribute. */
  code: DemoLangCode
  /** Two-letter code shown in the rail. */
  short: string
  /** The language's own name, in its own script. */
  native: string
  /** English name, for the accessible label when the UI is in English. */
  english: string
  dir: 'ltr' | 'rtl'
  /** The passage, translated. */
  text: string
}

/**
 * The source sentence. English is both the source and one of the six targets,
 * which is deliberate: the rotation starts and ends on it, so a visitor who
 * arrives mid-cycle still sees the sentence they can read.
 */
export const DEMO_SOURCE = 'en' as const

export const DEMO_LANGUAGES: readonly DemoLanguage[] = [
  {
    code: 'en',
    short: 'EN',
    native: 'English',
    english: 'English',
    dir: 'ltr',
    text: 'We arrived at dusk, when the city had begun to whisper instead of shout. The streets smelled of bread and rain, and for the first time in months I felt the quiet certainty that I had come to the right place.',
  },
  {
    code: 'fa',
    short: 'FA',
    native: 'فارسی',
    english: 'Persian',
    dir: 'rtl',
    text: 'غروب‌هنگام رسیدیم، وقتی شهر به‌جای فریاد کشیدن، آغاز کرده بود به نجوا کردن. کوچه‌ها بوی نان و باران می‌داد، و برای نخستین بار در ماه‌ها، آرامش یقینی را احساس کردم که به جای درست آمده‌ام.',
  },
  {
    code: 'ar',
    short: 'AR',
    native: 'العربية',
    english: 'Arabic',
    dir: 'rtl',
    text: 'وصلنا عند الغسق، حين أخذت المدينة تهمس بدل أن تصرخ. كانت الأزقة تفوح برائحة الخبز والمطر، وللمرة الأولى منذ أشهر، شعرت بيقين هادئ بأنني جئت إلى المكان الصحيح.',
  },
  {
    code: 'es',
    short: 'ES',
    native: 'Español',
    english: 'Spanish',
    dir: 'ltr',
    text: 'Llegamos al anochecer, cuando la ciudad había empezado a susurrar en lugar de gritar. Las calles olían a pan y a lluvia, y por primera vez en meses sentí la tranquila certeza de haber llegado al lugar correcto.',
  },
  {
    code: 'fr',
    short: 'FR',
    native: 'Français',
    english: 'French',
    dir: 'ltr',
    text: 'Nous sommes arrivés au crépuscule, lorsque la ville avait commencé à chuchoter plutôt qu’à crier. Les rues sentaient le pain et la pluie, et pour la première fois depuis des mois, j’ai ressenti la certitude paisible d’être au bon endroit.',
  },
  {
    code: 'de',
    short: 'DE',
    native: 'Deutsch',
    english: 'German',
    dir: 'ltr',
    text: 'Wir kamen in der Dämmerung an, als die Stadt begonnen hatte zu flüstern statt zu schreien. Die Straßen rochen nach Brot und Regen, und zum ersten Mal seit Monaten spürte ich die stille Gewissheit, am richtigen Ort angekommen zu sein.',
  },
] as const

/** How long each language holds the stage, in milliseconds. */
export const DEMO_INTERVAL_MS = 5200

/**
 * The next index in the rotation.
 *
 * Wraps, and is a plain function rather than inline arithmetic so the wrap
 * behaviour is testable without a timer. A `null` current index (nothing shown
 * yet) starts at the first language.
 */
export function nextDemoIndex(current: number | null, length = DEMO_LANGUAGES.length): number {
  if (length <= 0) return 0
  if (current === null || current < 0 || current >= length) return 0
  return (current + 1) % length
}
