import pygame
import random
import os

# -------------------- BASIC SETTINGS --------------------
pygame.init()
WIDTH, HEIGHT = 900, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pattern Recognition")

# --- put game inside photo's green screen ---
real_screen = screen  # keep a handle to the real display
PHOTO_PATH = "monitor.jpg"  # change if your file name is different

# load + scale the photo to window
try:
    bg_photo = pygame.image.load(PHOTO_PATH).convert()
    bg_photo = pygame.transform.smoothscale(bg_photo, (WIDTH, HEIGHT))
except Exception as e:
    print("Could not load photo:", e)
    bg_photo = None

# Green area of that photo (percent-based so it scales with your window)
GAME_RECT = pygame.Rect(
    int(WIDTH * 0.208),   # x
    int(HEIGHT * 0.168),  # y
    int(WIDTH * 0.595),   # w
    int(HEIGHT * 0.45),  # h
)

clock = pygame.time.Clock()
font_big = pygame.font.SysFont(None, 44)
font_med = pygame.font.SysFont(None, 28)

# Colors
BG = (20, 22, 40)
PANEL = (28, 30, 55)
WHITE = (235, 240, 255)
ACCENT = (110, 231, 255)
GREEN = (80, 200, 120)
RED = (230, 90, 90)
IDLE = (22, 26, 48)
REVEAL = (55, 90, 160)
PICK_FALLBACK = (42, 108, 122)
CORRECT = (40, 110, 70)
WRONG = (225, 0, 0)

LEVEL_SHAPES = [(2,2), (2,4), (3,4), (4,4), (4,5)]
LEVEL_REVEAL_TIME = [2500, 1800, 1200, 800, 600]
PATTERN_SIZES = [(2,4), (3,6), (5,8), (6,10), (8,12)]

# -------------------- SELECTION IMAGE --------------------
SELECT_IMAGE_PATH = "ryuzy.png"
select_img_original = None
select_img_scaled = None

def try_load_select_image():
    global select_img_original
    if os.path.exists(SELECT_IMAGE_PATH):
        try:
            img = pygame.image.load(SELECT_IMAGE_PATH).convert_alpha()
            select_img_original = img
        except Exception as e:
            print("Could not load selection image:", e)
            select_img_original = None
    else:
        select_img_original = None

def rescale_select_image(cell_size):
    global select_img_scaled
    if select_img_original is not None:
        select_img_scaled = pygame.transform.smoothscale(select_img_original, (cell_size, cell_size))
    else:
        select_img_scaled = None

try_load_select_image()

# -------------------- SIMPLE STATE --------------------
level_index = 0
score = 0
mistakes = 0
state = "reveal"  # NEW state added later: "congrats"

rows, cols = LEVEL_SHAPES[level_index]
grid_rects = []
targets = set()
picks = set()
feedback = {}
reveal_plan = []
reveal_step_index = 0
reveal_step_started = 0

# >>> NEW: constant feedback duration + dedicated timer
FEEDBACK_DURATION_MS = 1000
feedback_started = 0
# <<< NEW

# -------------------- GRID LAYOUT --------------------
def build_grid_rects(rows, cols):
    area = pygame.Rect(50, 120, WIDTH-100, HEIGHT-180)
    gap = 8
    max_w = (area.width - gap*(cols-1)) // cols
    max_h = (area.height - gap*(rows-1)) // rows
    size = min(max_w, max_h)
    total_w = cols*size + gap*(cols-1)
    total_h = rows*size + gap*(rows-1)
    start_x = area.x + (area.width - total_w)//2
    start_y = area.y + (area.height - total_h)//2
    rects = []
    for r in range(rows):
        for c in range(cols):
            x = start_x + c*(size+gap)
            y = start_y + r*(size+gap)
            rects.append(pygame.Rect(x, y, size, size))
    return rects

# -------------------- PATTERN MAKING --------------------
def neighbors(r, c, rows, cols):
    out = []
    for dr, dc in [(1,0),(-1,0),(0,1),(0,-1)]:
        rr, cc = r+dr, c+dc
        if 0 <= rr < rows and 0 <= cc < cols:
            out.append((rr,cc))
    return out

def cluster_pattern(rows, cols, k):
    start = (random.randrange(rows), random.randrange(cols))
    chosen = {start}
    while len(chosen) < k:
        base = random.choice(list(chosen))
        nbs = [p for p in neighbors(base[0], base[1], rows, cols) if p not in chosen]
        if nbs:
            chosen.add(random.choice(nbs))
        else:
            chosen.add((random.randrange(rows), random.randrange(cols)))
    return chosen

def scatter_pattern(rows, cols, k):
    all_cells = [(r,c) for r in range(rows) for c in range(cols)]
    random.shuffle(all_cells)
    chosen = []
    for rc in all_cells:
        ok = True
        for (r,c) in chosen:
            if abs(rc[0]-r) + abs(rc[1]-c) <= 1:
                ok = False
                break
        if ok:
            chosen.append(rc)
        if len(chosen) == k:
            break
    if len(chosen) < k:
        for rc in all_cells:
            if rc not in chosen:
                chosen.append(rc)
                if len(chosen) == k:
                    break
    return set(chosen)

def pick_targets(rows, cols, level_index):
    lo, hi = PATTERN_SIZES[level_index]
    hi = min(hi, rows*cols)
    k = random.randint(lo, hi)
    scatter_chance = [0.2, 0.4, 0.6, 0.75, 0.9][level_index]
    if random.random() < scatter_chance:
        return scatter_pattern(rows, cols, k)
    else:
        return cluster_pattern(rows, cols, k)

# -------------------- REVEAL PLANS --------------------
def make_reveal_plan(rows, cols, targets, level_index):
    mode = random.choice(["full", "sides", "sections4", "snake"])
    plan = []

    if mode == "full":
        plan.append({"cells": set(targets), "time": LEVEL_REVEAL_TIME[level_index]})
    elif mode == "sides":
        half = cols // 2
        left = {(r,c) for (r,c) in targets if c < half}
        right = {(r,c) for (r,c) in targets if c >= half}
        order = [("L", left), ("R", right)]
        random.shuffle(order)
        for _name, subset in order:
            if subset:
                plan.append({"cells": subset, "time": 500})
        if not plan:
            plan.append({"cells": set(targets), "time": 800})
    elif mode == "sections4":
        sections = []
        for r in range(0, rows, 2):
            for c in range(0, cols, 2):
                block = []
                for dr in (0,1):
                    for dc in (0,1):
                        rr, cc = r+dr, c+dc
                        if 0 <= rr < rows and 0 <= cc < cols:
                            block.append((rr,cc))
                sections.append(block)
        random.shuffle(sections)
        for block in sections:
            part = set([rc for rc in block if rc in targets])
            if part:
                plan.append({"cells": part, "time": 300})
        if not plan:
            plan.append({"cells": set(targets), "time": 700})
    elif mode == "snake":
        for r in range(rows):
            cols_range = range(cols) if r % 2 == 0 else range(cols-1, -1, -1)
            for c in cols_range:
                if (r,c) in targets:
                    plan.append({"cells": {(r,c)}, "time": 300})
        if not plan:
            plan.append({"cells": set(targets), "time": 700})
    return plan

# -------------------- LEVEL / ROUND SETUP --------------------
def build_round():
    global rows, cols, grid_rects, targets, picks, feedback
    global reveal_plan, reveal_step_index, reveal_step_started, state
    global feedback_started  # NEW

    rows, cols = LEVEL_SHAPES[level_index]
    grid_rects = build_grid_rects(rows, cols)
    if grid_rects:
        cell_size = grid_rects[0].width
        rescale_select_image(cell_size)

    targets = pick_targets(rows, cols, level_index)
    picks = set()
    feedback = {}
    reveal_plan = make_reveal_plan(rows, cols, targets, level_index)
    reveal_step_index = 0
    reveal_step_started = pygame.time.get_ticks()
    feedback_started = 0  # NEW: reset feedback timer
    state = "reveal"

def reset_all():
    global level_index, score, mistakes, state
    level_index = 0
    score = 0
    mistakes = 0
    state = "reveal"
    build_round()

# -------------------- DRAWING --------------------
def draw_hud(surface):
    top = pygame.Rect(40, 30, WIDTH-80, 70)
    pygame.draw.rect(surface, PANEL, top, border_radius=12)
    title = font_big.render("Ryuzy Pattern Recognition", True, WHITE)
    surface.blit(title, (top.x+12, top.y+12))

    info1 = font_med.render(f"Level: {level_index+1}/5", True, ACCENT)
    info2 = font_med.render(f"Score: {score}", True, WHITE)
    life_left = 3 - mistakes
    life_text = font_med.render(f"Lives: {max(0, life_left)}", True, GREEN if life_left>=1 else RED)
    surface.blit(info1, (top.right-260, top.y+12))
    surface.blit(info2, (top.right-260, top.y+38))
    surface.blit(life_text, (top.right-120, top.y+25))

def draw_board(surface, lit_cells=None):
    if lit_cells is None:
        lit_cells = set()
    for i, rect in enumerate(grid_rects):
        r = i // cols
        c = i % cols
        color = IDLE
        if state == "reveal" and (r,c) in lit_cells:
            color = REVEAL
        elif state == "feedback" and (r,c) in feedback:
            color = CORRECT if feedback[(r,c)] == "correct" else WRONG
        pygame.draw.rect(surface, color, rect, border_radius=8)
        pygame.draw.rect(surface, (255,255,255,40), rect, 1, border_radius=8)
        if state in ("input", "feedback") and (r,c) in picks:
            if select_img_scaled is not None:
                surface.blit(select_img_scaled, rect.topleft)
            else:
                pygame.draw.rect(surface, PICK_FALLBACK, rect, border_radius=8)

# -------------------- CHECK ANSWER --------------------
def check_answer():
    global score, mistakes, state, feedback_started
    # sets
    correct = targets & picks
    wrong_picked = picks - targets
    missed = targets - picks

    # --- build feedback colors ---
    feedback.clear()
    for rc in correct:
        feedback[rc] = "correct"
    for rc in wrong_picked:
        feedback[rc] = "wrong"
    for rc in missed:
        feedback[rc] = "wrong"

    # --- STRICT correctness: must match exactly ---
    is_perfect = (picks == targets)

    if is_perfect:
        gain = len(targets) + (level_index + 1) * 2
        score += gain
        state = "feedback"
        feedback_started = pygame.time.get_ticks()
    else:
        mistakes += 1
        if mistakes >= 4:
            state = "gameover"
        else:
            state = "feedback"
            feedback_started = pygame.time.get_ticks()

# -------------------- MAIN --------------------
def main():
    global state, reveal_step_index, reveal_step_started, level_index, feedback_started  # NEW
    reset_all()
    running = True
    while running:
        clock.tick(120)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and state == "input":
                mx, my = event.pos
                if GAME_RECT.collidepoint(mx, my):
                    sx = (mx - GAME_RECT.x) * WIDTH / GAME_RECT.width
                    sy = (my - GAME_RECT.y) * HEIGHT / GAME_RECT.height
                    pos = (sx, sy)
                    for i, rect in enumerate(grid_rects):
                        if rect.collidepoint(pos):
                            r = i // cols
                            c = i % cols
                            if (r,c) in picks:
                                picks.remove((r,c))
                            else:
                                picks.add((r,c))
                            break
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN and state == "input":
                    check_answer()
                elif event.key == pygame.K_SPACE and state in ("gameover", "congrats"):  # updated
                    reset_all()

        # --------- RENDER ---------
        game_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        game_surface.fill(BG)
        draw_hud(game_surface)

        if state == "reveal":
            now = pygame.time.get_ticks()
            if reveal_step_index < len(reveal_plan):
                step = reveal_plan[reveal_step_index]
                lit = step["cells"]
                draw_board(game_surface, lit_cells=lit)
                if now - reveal_step_started >= step["time"]:
                    reveal_step_index += 1
                    reveal_step_started = now
            else:
                state = "input"
                draw_board(game_surface)

        elif state == "input":
            draw_board(game_surface)

        elif state == "feedback":
            draw_board(game_surface)
            # >>> constant feedback duration
            if feedback_started == 0:
                feedback_started = pygame.time.get_ticks()
            if pygame.time.get_ticks() - feedback_started > FEEDBACK_DURATION_MS:
                feedback_started = 0
                if mistakes >= 4:
                    state = "gameover"
                else:
                    any_wrong = any(v == "wrong" for v in feedback.values())
                    if not any_wrong:
                        # final level congrats
                        if level_index == len(LEVEL_SHAPES)-1:
                            state = "congrats"
                        elif level_index < len(LEVEL_SHAPES)-1:
                            level_index += 1
                            build_round()
                    else:
                        build_round()

        elif state == "gameover":
            draw_board(game_surface)
            over1 = font_big.render("GAME OVER", True, RED)
            over2 = font_med.render(f"Final Score: {score}", True, WHITE)
            over3 = font_med.render("Press SPACE to restart", True, ACCENT)
            game_surface.blit(over1, over1.get_rect(center=(WIDTH//2, HEIGHT//2 - 20)))
            game_surface.blit(over2, over2.get_rect(center=(WIDTH//2, HEIGHT//2 + 15)))
            game_surface.blit(over3, over3.get_rect(center=(WIDTH//2, HEIGHT//2 + 50)))

        # 🎉 NEW: Congratulations screen
        elif state == "congrats":
            draw_board(game_surface)
            msg1 = font_big.render("Congratulations!", True, GREEN)
            msg2 = font_med.render("You completed all 5 levels!", True, WHITE)
            msg3 = font_med.render("Press SPACE to restart", True, ACCENT)
            game_surface.blit(msg1, msg1.get_rect(center=(WIDTH//2, HEIGHT//2 - 20)))
            game_surface.blit(msg2, msg2.get_rect(center=(WIDTH//2, HEIGHT//2 + 15)))
            game_surface.blit(msg3, msg3.get_rect(center=(WIDTH//2, HEIGHT//2 + 50)))

        # --------- COMPOSITE ---------
        if bg_photo:
            real_screen.blit(bg_photo, (0, 0))
        else:
            real_screen.fill((0, 0, 0))
        scaled = pygame.transform.smoothscale(game_surface, (GAME_RECT.width, GAME_RECT.height))
        real_screen.blit(scaled, GAME_RECT.topleft)
        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
