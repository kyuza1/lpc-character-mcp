"""User-facing messages in English (default) and Portuguese.

Set LPC_LANG=pt (or pt-BR) for Portuguese. The language is read on every call, so it can
change without restarting.
"""
import os

MESSAGES = {
    # errors
    "unknown_item": {"en": "unknown item: {id}", "pt": "item desconhecido: {id}"},
    "bad_body": {"en": "body_type must be one of {bodies}", "pt": "body_type deve ser um de {bodies}"},
    "no_layers": {"en": "no layers found for this combination",
                  "pt": "nenhuma camada encontrada para essa combinação"},
    "bad_layout": {"en": "layout must be 'standard' or 'compact'",
                   "pt": "layout deve ser 'standard' ou 'compact'"},
    "bad_split": {"en": "invalid split: {bad}. Use animation, item and/or frame.",
                  "pt": "split inválido: {bad}. Use animation, item e/ou frame."},
    "bad_export": {"en": "invalid export: {bad}. Use {valid}.", "pt": "export inválido: {bad}. Use {valid}."},
    "unknown_animation": {"en": "unknown animation: {anim}. Use one of {valid} or an oversized one.",
                          "pt": "animação desconhecida: {anim}. Use uma de {valid} ou uma especial."},
    "animation_not_available": {"en": "animation '{anim}' does not exist for these items: {available}",
                                "pt": "a animação '{anim}' não existe para esses itens: {available}"},
    "no_git": {"en": "lpc-mcp: Git was not found. Install it from https://git-scm.com/downloads and run "
                     "again (it is only used to download the item definitions).",
               "pt": "lpc-mcp: o Git não foi encontrado. Instale em https://git-scm.com/downloads e rode "
                     "de novo (ele só é usado para baixar as definições dos itens)."},
    "download_failed": {"en": "lpc-mcp: could not download the definitions from GitHub (check your "
                              "internet connection).",
                        "pt": "lpc-mcp: falha ao baixar as definições do GitHub (verifique a internet)."},
    # warnings
    "replaced_same_type": {"en": "{new} replaced {old} (same type: {type})",
                           "pt": "{new} substituiu {old} (mesmo tipo: {type})"},
    "template_mismatch": {"en": "{id} does not match the chosen {need} and was skipped",
                          "pt": "{id} não combina com o {need} escolhido e foi ignorado"},
    # animation report
    "report_complete": {"en": "All animations are complete for every item.",
                        "pt": "Todas as animações estão completas para todos os itens."},
    "report_header": {"en": "WARNING: not every animation is complete: ",
                      "pt": "ATENÇÃO: nem todas as animações ficaram completas: "},
    "report_body": {"en": "the LPC {body} body has no {anims} (no item can fix this; use another body "
                          "type if you need them)",
                    "pt": "o corpo {body} do LPC não tem {anims} (nenhuma peça resolve; use outro tipo de "
                          "corpo se precisar delas)"},
    "report_item": {"en": "{name} has no {anims}", "pt": "{name} não tem {anims}"},
    "report_alternatives": {"en": " (similar complete items: {alts})",
                            "pt": " (completos parecidos: {alts})"},
    "report_no_alternative": {"en": " (no complete alternative of the same type)",
                              "pt": " (não há alternativa completa do mesmo tipo)"},
    "report_hint": {"en": " Use prefer_complete=True to swap them for complete items.",
                    "pt": " Use prefer_complete=True para trocar por itens completos."},
    # license check
    "license_drm_ok": {"en": "Every art part allows CC0 or OGA-BY: fine for DRM stores (Steam, App Store).",
                       "pt": "Todas as partes da arte aceitam CC0 ou OGA-BY: pode usar em lojas com DRM (Steam, App Store)."},
    "license_drm_no": {"en": "{n} art part(s) do not allow CC0/OGA-BY: avoid DRM stores or swap them "
                             "(search_items with licenses=[\"CC0\", \"OGA-BY\"]).",
                       "pt": "{n} parte(s) da arte não aceitam CC0/OGA-BY: evite lojas com DRM ou troque "
                             "(search_items com licenses=[\"CC0\", \"OGA-BY\"])."},
    "license_share_alike": {"en": "Some parts are only CC-BY-SA/GPL: share changed art under the same license.",
                            "pt": "Algumas partes são só CC-BY-SA/GPL: compartilhe a arte alterada pela mesma licença."},
    "license_blocked": {"en": "{id} is not available under the licenses {allowed}",
                        "pt": "{id} não está disponível nas licenças {allowed}"},
    # credits file
    "credits_header": {"en": "Art from the Universal LPC Spritesheet Character Generator.\n"
                             "When you use these images, credit the authors below according to the licenses.\n\n",
                       "pt": "Artes do Universal LPC Spritesheet Character Generator.\n"
                             "Ao usar estas imagens, dê crédito aos autores abaixo conforme as licenças.\n\n"},
    "credits_statement": {
        "en": "Credits screen text (paste it in your game):\n"
              "Sprites by: {authors}\n"
              "Sprites from the Liberated Pixel Cup collection on OpenGameArt.org: "
              "http://opengameart.org/content/lpc-collection\n"
              "License(s): {licenses}\n"
              "Detailed credits: {file}",
        "pt": "Texto para a tela de créditos (cole no seu jogo):\n"
              "Sprites by: {authors}\n"
              "Sprites from the Liberated Pixel Cup collection on OpenGameArt.org: "
              "http://opengameart.org/content/lpc-collection\n"
              "License(s): {licenses}\n"
              "Detailed credits: {file}"},
    "credits_notes": {"en": "Notes", "pt": "Notas"},
    "credits_authors": {"en": "Authors", "pt": "Autores"},
    "credits_licenses": {"en": "Licenses", "pt": "Licenças"},
    # exporters
    "godot_in_project": {"en": "Already in the project: use {res} as Sprite Frames of an AnimatedSprite2D",
                         "pt": "Já está no projeto: use {res} em Sprite Frames de um AnimatedSprite2D"},
    "godot_copy": {"en": "Copy {png} and {tres} to {res_dir} in your Godot 4 project and use the .tres as "
                         "Sprite Frames of an AnimatedSprite2D",
                   "pt": "Copie {png} e {tres} para {res_dir} no projeto Godot 4 e use o .tres em Sprite "
                         "Frames de um AnimatedSprite2D"},
    "godot_anims": {"en": " (animations: walk_down, walk_up, idle_left...).",
                    "pt": " (animações: walk_down, walk_up, idle_left...)."},
    "unity_how": {"en": "Copy {png}, {png}.meta, {ctrl}(.meta) and the {folder} folder to Assets/ in Unity "
                        "(or generate with output_dir inside Assets/). Put {ctrl} in the Animator of an "
                        "object with a SpriteRenderer and switch animations with animator.Play(\"walk_left\").",
                  "pt": "Copie {png}, {png}.meta, {ctrl}(.meta) e a pasta {folder} para Assets/ no Unity (ou "
                        "gere com output_dir dentro de Assets/). Coloque o {ctrl} no Animator de um objeto "
                        "com SpriteRenderer e troque a animação com animator.Play(\"walk_left\")."},
    "web_how": {"en": "Phaser 3: this.load.atlas('char', '{png}', '{json}') and create the animations from "
                      "atlas.animations. PixiJS: Assets.load('{json}') and use sheet.animations['walk_down'] "
                      "in an AnimatedSprite. Open {html} in a browser to see it.",
                "pt": "Phaser 3: this.load.atlas('char', '{png}', '{json}') e crie as animações a partir de "
                      "atlas.animations. PixiJS: Assets.load('{json}') e use sheet.animations['walk_down'] "
                      "num AnimatedSprite. Abra {html} no navegador para ver."},
    "site_how": {"en": "On the site, copy the file contents and click Import from Clipboard (JSON).",
                 "pt": "No site, copie o conteúdo do arquivo e clique em Import from Clipboard (JSON)."},
    # command line
    "cli_ready": {"en": "lpc-character-mcp ready: {n} items.", "pt": "lpc-character-mcp pronto: {n} itens."},
    "cli_defs": {"en": "Definitions in {path}", "pt": "Definições em {path}"},
    "cli_out": {"en": "Characters will be saved to {path}", "pt": "Personagens serão salvos em {path}"},
    "cli_cleared": {"en": "{files} files deleted, {mb} MB freed (cache now: {now} MB in {dir})",
                    "pt": "{files} arquivos apagados, {mb} MB liberados (cache agora: {now} MB em {dir})"},
    "cli_where": {"en": "data:        {data}\ndefinitions: {defs}\ncache:       {cache}\ncharacters:  {out}",
                  "pt": "dados:       {data}\ndefinições:  {defs}\ncache:       {cache}\npersonagens: {out}"},
    # web demo page (__T:key__ tokens in demo_template.html)
    "demo_html_lang": {"en": "en", "pt": "pt-BR"},
    "demo_title": {"en": "LPC character", "pt": "Personagem LPC"},
    "demo_canvas_label": {"en": "Animated character", "pt": "Personagem animado"},
    "demo_controls_label": {"en": "Controls", "pt": "Controles"},
    "demo_animation": {"en": "Animation", "pt": "Animação"},
    "demo_direction": {"en": "Direction", "pt": "Direção"},
    "demo_up": {"en": "Up", "pt": "Cima"},
    "demo_left": {"en": "Left", "pt": "Esquerda"},
    "demo_down": {"en": "Down", "pt": "Baixo"},
    "demo_right": {"en": "Right", "pt": "Direita"},
    "demo_pause": {"en": "Pause / resume", "pt": "Pausar / continuar"},
    "demo_keys": {"en": "Play: <kbd>↑</kbd><kbd>←</kbd><kbd>↓</kbd><kbd>→</kbd> or <kbd>WASD</kbd> walk · "
                        "<kbd>Shift</kbd> run · <kbd>Space</kbd> attack",
                  "pt": "Jogar: <kbd>↑</kbd><kbd>←</kbd><kbd>↓</kbd><kbd>→</kbd> ou <kbd>WASD</kbd> anda · "
                        "<kbd>Shift</kbd> corre · <kbd>Espaço</kbd> ataca"},
    "demo_no_art": {"en": "No art in this animation/direction.", "pt": "Nenhuma arte nesta animação/direção."},
    "demo_lacking": {"en": "No art in this animation: %s.", "pt": "Sem arte nesta animação: %s."},
    "demo_size_mismatch": {"en": "The image is %1, but the atlas expects %2. Generate the image and the "
                                 "atlas again together.",
                           "pt": "A imagem tem %1, mas o atlas espera %2. Gere de novo a imagem e o atlas juntos."},
    "demo_load_error": {"en": "Could not load %s. Keep this page in the same folder as the image and open "
                              "it through a local server (e.g. python -m http.server).",
                        "pt": "Não consegui carregar %s. Deixe esta página na mesma pasta da imagem e abra "
                              "por um servidor local (ex.: python -m http.server)."},
}


def lang():
    value = os.environ.get("LPC_LANG", "en").lower()
    return "pt" if value.startswith("pt") else "en"


def t(key, **kwargs):
    """Message `key` in the current language, formatted with kwargs."""
    return MESSAGES[key][lang()].format(**kwargs)
