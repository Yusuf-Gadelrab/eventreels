from dataclasses import dataclass

@dataclass
class TitleStyle:
    font_size: int = 84
    y_expr: str = "h*0.12"
    duration: float = 2.5

@dataclass
class TemplateConfig:
    min_seg: float = 1.5
    max_seg: float = 6.0
    fade: float = 0.2
    title: TitleStyle = None

    def __post_init__(self):
        if self.title is None:
            self.title = TitleStyle()

TEMPLATES = {
    "auto": TemplateConfig(),
    "rush": TemplateConfig(min_seg=0.8, max_seg=2.5, fade=0.05, title=TitleStyle(font_size=110, y_expr="(h-text_h)/2", duration=1.5)),
    "gameday": TemplateConfig(min_seg=1.2, max_seg=4.0, fade=0.1, title=TitleStyle(font_size=96, y_expr="h*0.8", duration=2.0)),
    "formal": TemplateConfig(min_seg=2.5, max_seg=8.0, fade=0.5, title=TitleStyle(font_size=72, y_expr="h*0.1", duration=4.0)),
    "hackathon": TemplateConfig(min_seg=1.0, max_seg=5.0, fade=0.2, title=TitleStyle(font_size=84, y_expr="h*0.15", duration=3.0)),
}

def get_template(name: str | None) -> TemplateConfig:
    if not name or name not in TEMPLATES:
        return TEMPLATES["auto"]
    return TEMPLATES[name]
