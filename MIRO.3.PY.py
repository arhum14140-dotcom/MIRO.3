# miro_like_mibro_nosignin.py
"""
M.I BRO — Miro-like Whiteboard (Tkinter)
----------------------------------------
• Sign-in / Register system (optional, not compulsory)
• Both “Sign In” and “Sign Out” buttons on the top bar
• Right-side colorful toolbar, white background
• Tools: Pen, Eraser, Rectangle, Oval, Text, Sticky, Connector, Select
• Undo / Redo, Save / Load JSON, Export PNG
"""

import tkinter as tk
from tkinter import simpledialog, colorchooser, filedialog, messagebox
import sqlite3, os, json, time, uuid, hashlib, io, platform
from PIL import ImageGrab

DB_FILE = "users.db"

# ---------- Authentication ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        salt TEXT NOT NULL,
        pw_hash TEXT NOT NULL,
        created_at REAL
    )""")
    conn.commit(); conn.close()

def hash_pw(p, s): return hashlib.sha256((s + p).encode()).hexdigest()

def register_user(u, p):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE username=?", (u,))
    if cur.fetchone():
        conn.close(); return False, "Username already exists."
    salt = uuid.uuid4().hex
    cur.execute("INSERT INTO users VALUES (?,?,?,?)", (u, salt, hash_pw(p, salt), time.time()))
    conn.commit(); conn.close(); return True, "Registered."

def login_user(u, p):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT salt,pw_hash FROM users WHERE username=?", (u,))
    row = cur.fetchone(); conn.close()
    if not row: return False
    return hash_pw(p, row[0]) == row[1]

# ---------- Snapshot ----------
class History:
    def __init__(self): self.data=[]; self.ptr=-1
    def push(self, s): self.data=self.data[:self.ptr+1]; self.data.append(s); self.ptr=len(self.data)-1
    def undo(self): 
        if self.ptr>0: self.ptr-=1; return self.data[self.ptr]
    def redo(self): 
        if self.ptr+1<len(self.data): self.ptr+=1; return self.data[self.ptr]
    def current(self): return self.data[self.ptr] if self.ptr>=0 else None

# ---------- App ----------
class MIBro(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("M.I BRO — Whiteboard")
        self.geometry("1200x800")
        self.minsize(900,600)
        init_db()
        self.user=None
        self.tool=tk.StringVar(value="pen")
        self.color="#1f2937"; self.stroke=tk.IntVar(value=3); self.font=tk.IntVar(value=16)
        self.scale=1.0; self.history=History()
        self.cur=None; self.points=[]
        self._build_ui(); self._bind_events()

    # ---------- UI ----------
    def _build_ui(self):
        top=tk.Frame(self,bg="white",height=60); top.pack(side=tk.TOP,fill=tk.X)
        tk.Label(top,text="M.I BRO",bg="white",fg="#0b1220",font=("Helvetica",20,"bold")).pack(side=tk.LEFT,padx=10)
        self.user_lbl=tk.Label(top,text="Not signed in",bg="white",fg="#444")
        self.user_lbl.pack(side=tk.RIGHT,padx=10)
        tk.Button(top,text="Sign In",command=self._show_login,bg="#e8f0fe").pack(side=tk.RIGHT,padx=5)
        tk.Button(top,text="Sign Out",command=self._signout,bg="#fee8e8").pack(side=tk.RIGHT,padx=5)

        body=tk.Frame(self,bg="white"); body.pack(fill=tk.BOTH,expand=True)
        self.canvas=tk.Canvas(body,bg="white",highlightthickness=0); self.canvas.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        R=12000; self.canvas.config(scrollregion=(-R,-R,R,R))

        bar=tk.Frame(body,width=190,bg="#f7f9fc"); bar.pack(side=tk.RIGHT,fill=tk.Y)
        tk.Label(bar,text="TOOLS",bg="#f7f9fc",fg="#0b1220",font=("Arial",11,"bold")).pack(pady=8)
        def btn(txt,val,bg): tk.Radiobutton(bar,text=txt,variable=self.tool,value=val,
            indicatoron=False,width=15,padx=6,pady=5,anchor="w",bg=bg,bd=0).pack(pady=2,padx=6)
        btn("Pen ✏️","pen","#d1eaff"); btn("Eraser 🧽","eraser","#ffe6e6")
        btn("Rectangle ▭","rect","#eaf6df"); btn("Oval ◯","oval","#fff2cc")
        btn("Text 🔤","text","#f3e6ff"); btn("Sticky 🗒️","sticky","#fff0d6")
        btn("Connector ➜","connector","#e6f7ff"); btn("Select 🔍","select","#f0f0f0")
        tk.Button(bar,text="Color",command=self._pick,bg="#fff").pack(pady=6)
        self.prev=tk.Label(bar,bg=self.color,width=15,height=1,bd=1,relief=tk.SUNKEN); self.prev.pack()
        tk.Label(bar,text="Stroke",bg="#f7f9fc").pack(); tk.Spinbox(bar,from_=1,to=30,textvariable=self.stroke,width=5).pack()
        tk.Label(bar,text="Font",bg="#f7f9fc").pack(); tk.Spinbox(bar,from_=8,to=60,textvariable=self.font,width=5).pack()
        for lbl,cmd in [("Undo",self._undo),("Redo",self._redo),("Clear",self._clear),
                        ("Save JSON",self._save),("Load JSON",self._load),("Export PNG",self._export)]:
            tk.Button(bar,text=lbl,command=cmd,width=15,bg="#fff").pack(pady=4)
        tk.Label(self,text="Tips: Space+drag=pan | Wheel=zoom | Double-click text to edit",
                 bg="white",fg="#777").pack(side=tk.BOTTOM,fill=tk.X)

    # ---------- Events ----------
    def _bind_events(self):
        c=self.canvas
        c.bind("<ButtonPress-1>",self._down)
        c.bind("<B1-Motion>",self._move)
        c.bind("<ButtonRelease-1>",self._up)
        c.bind("<Double-Button-1>",self._dbl)
        c.bind("<ButtonPress-2>",self._pan_start)
        c.bind("<B2-Motion>",self._pan_move)
        c.bind("<ButtonRelease-2>",self._pan_end)
        self.bind("<KeyPress-space>",lambda e:self.canvas.config(cursor="fleur"))
        self.bind("<KeyRelease-space>",lambda e:self.canvas.config(cursor=""))
        c.bind("<MouseWheel>",self._zoom)
        self.bind("<Control-z>",lambda e:self._undo())
        self.bind("<Control-y>",lambda e:self._redo())
        self.bind("<Delete>",lambda e:self._del())

    # ---------- Tool logic ----------
    def _pick(self):
        c=colorchooser.askcolor(color=self.color)[1]
        if c:self.color=c; self.prev.config(bg=c)

    def _down(self,e):
        x,y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y)
        t=self.tool.get()
        if self.canvas["cursor"]=="fleur" or e.num==2: self._pan_start(e); return
        if t=="pen":
            self.points=[x,y]; self.cur=self.canvas.create_line(x,y,x+1,y+1,fill=self.color,width=self.stroke.get(),capstyle=tk.ROUND,smooth=True,splinesteps=36,tags="draw")
        elif t=="eraser":
            self.points=[x,y]; self.cur=self.canvas.create_line(x,y,x+1,y+1,fill="white",width=max(8,self.stroke.get()*3),capstyle=tk.ROUND,smooth=True,tags="draw")
        elif t in("rect","oval"):
            f=self.canvas.create_rectangle if t=="rect" else self.canvas.create_oval
            self.cur=f(x,y,x,y,outline=self.color,width=self.stroke.get(),tags="draw")
        elif t=="text":
            s=simpledialog.askstring("Text","Enter text:"); 
            if s:self.canvas.create_text(x,y,text=s,anchor="nw",font=("Arial",self.font.get()),fill=self.color,tags="draw"); self._snap()
        elif t=="sticky":
            r=self.canvas.create_rectangle(x,y,x+260,y+150,fill="#fff5b1",outline="#e6c200",width=2,tags="draw")
            self.canvas.create_text(x+8,y+8,text="Sticky\nDouble-click to edit",anchor="nw",font=("Arial",self.font.get()),tags="draw"); self._snap()
        elif t=="connector":
            self.start=(x,y); self.cur=self.canvas.create_line(x,y,x,y,fill=self.color,width=self.stroke.get(),arrow=tk.LAST,tags="draw")
        elif t=="select":
            self.selstart=(x,y); self.selbox=self.canvas.create_rectangle(x,y,x,y,dash=(3,3),outline="#333")

    def _move(self,e):
        x,y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y); t=self.tool.get()
        if getattr(self,"_panning",False): self._pan_move(e); return
        if t in("pen","eraser") and self.cur:
            self.points.extend([x,y]); self.canvas.coords(self.cur,*self.points)
        elif t in("rect","oval") and self.cur:
            x0,y0=self.canvas.coords(self.cur)[:2]; self.canvas.coords(self.cur,x0,y0,x,y)
        elif t=="connector" and self.cur:
            sx,sy=self.start; self.canvas.coords(self.cur,sx,sy,x,y)
        elif t=="select" and hasattr(self,"selbox"):
            x0,y0=self.selstart; self.canvas.coords(self.selbox,x0,y0,x,y)

    def _up(self,e):
        t=self.tool.get()
        if getattr(self,"_panning",False): self._pan_end(e); return
        if t in("pen","eraser","rect","oval","connector") and self.cur:
            self._snap(); self.cur=None; self.points=[]
        elif t=="select" and hasattr(self,"selbox"):
            self.canvas.delete("selrect")
            box=self.canvas.coords(self.selbox); self.canvas.delete(self.selbox)
            found=self.canvas.find_enclosed(*box)
            if found:
                xs,ys=[],[]
                for i in found:
                    b=self.canvas.bbox(i)
                    if b: xs.extend([b[0],b[2]]); ys.extend([b[1],b[3]])
                if xs and ys:
                    bb=(min(xs),min(ys),max(xs),max(ys))
                    self.canvas.create_rectangle(*bb,outline="#00a3ff",width=2,dash=(4,2),tags="selrect")

    def _dbl(self,e):
        x,y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y)
        for i in self.canvas.find_overlapping(x,y,x,y):
            if self.canvas.type(i)=="text":
                cur=self.canvas.itemcget(i,"text")
                new=simpledialog.askstring("Edit","Edit:",initialvalue=cur)
                if new:self.canvas.itemconfigure(i,text=new); self._snap()

    # ---------- Pan / Zoom ----------
    def _pan_start(self,e): self._panning=True; self.canvas.config(cursor="fleur"); self._pan_last=(e.x_root,e.y_root)
    def _pan_move(self,e):
        dx=e.x_root-self._pan_last[0]; dy=e.y_root-self._pan_last[1]
        for i in self.canvas.find_all(): self.canvas.move(i,dx,dy)
        self._pan_last=(e.x_root,e.y_root)
    def _pan_end(self,e): self._panning=False; self.canvas.config(cursor="")
    def _zoom(self,e):
        delta=e.delta if hasattr(e,"delta") else (120 if e.num==4 else -120)
        f=1+0.0015*delta; new=self.scale*f
        if .2<new<3:
            self.scale=new; cx,cy=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y)
            self.canvas.scale("all",cx,cy,f,f)

    # ---------- Utilities ----------
    def _serialize(self,i):
        t=self.canvas.type(i); c=self.canvas.coords(i)
        props={k:self.canvas.itemcget(i,k) for k in("fill","outline","width","arrow","font","text") if self.canvas.itemcget(i,k)}
        return {"t":t,"c":c,"p":props}
    def _deserialize(self,o):
        t=o["t"]; c=o["c"]; p=o["p"]
        if t=="rectangle": self.canvas.create_rectangle(*c,**p)
        elif t=="oval": self.canvas.create_oval(*c,**p)
        elif t=="line": self.canvas.create_line(*c,**p)
        elif t=="text": self.canvas.create_text(*c,**p)
    def _snap(self):
        data=[self._serialize(i) for i in self.canvas.find_all()]
        self.history.push({"d":data,"s":self.scale})
    def _undo(self):
        s=self.history.undo(); 
        if s:self.canvas.delete("all"); [self._deserialize(o) for o in s["d"]]
    def _redo(self):
        s=self.history.redo(); 
        if s:self.canvas.delete("all"); [self._deserialize(o) for o in s["d"]]
    def _clear(self):
        if messagebox.askyesno("Clear","Clear canvas?"): self.canvas.delete("all"); self._snap()
    def _save(self):
        fn=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")])
        if not fn:return
        data=[self._serialize(i) for i in self.canvas.find_all()]
        json.dump({"data":data},open(fn,"w"),indent=2)
    def _load(self):
        fn=filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not fn:return
        d=json.load(open(fn)); self.canvas.delete("all")
        [self._deserialize(o) for o in d["data"]]; self._snap()
    def _export(self):
        self.update()
        x=self.canvas.winfo_rootx(); y=self.canvas.winfo_rooty()
        w=x+self.canvas.winfo_width(); h=y+self.canvas.winfo_height()
        img=ImageGrab.grab(bbox=(x,y,w,h))
        fn=filedialog.asksaveasfilename(defaultextension=".png",filetypes=[("PNG","*.png")])
        if fn: img.save(fn); messagebox.showinfo("Export","Saved PNG.")
    def _del(self):
        for i in self.canvas.find_withtag("selrect"): 
            box=self.canvas.bbox(i); found=self.canvas.find_enclosed(*box)
            for j in found:self.canvas.delete(j)
            self.canvas.delete(i)
        self._snap()

    # ---------- Sign in / out ----------
    def _show_login(self):
        dlg=tk.Toplevel(self); dlg.title("Sign In / Register"); dlg.geometry("360x230"); dlg.resizable(False,False)
        tk.Label(dlg,text="M.I BRO — Sign In",font=("Helvetica",14,"bold")).pack(pady=8)
        f=tk.Frame(dlg); f.pack()
        tk.Label(f,text="Username").grid(row=0,column=0,sticky="w"); u=tk.Entry(f,width=26); u.grid(row=0,column=1,pady=4)
        tk.Label(f,text="Password").grid(row=1,column=0,sticky="w"); p=tk.Entry(f,width=26,show="*"); p.grid(row=1,column=1,pady=4)
        msg=tk.Label(dlg,text="",fg="red"); msg.pack()
        def do_login():
            if login_user(u.get(),p.get()):
                self.user=u.get(); self.user_lbl.config(text=f"Signed in: {self.user}")
                dlg.destroy()
            else: msg.config(text="Invalid credentials.")
        def do_reg():
            ok,info=register_user(u.get(),p.get())
            msg.config(text=info if not ok else "Registered. Sign in now.")
        tk.Button(dlg,text="Sign In",command=do_login,width=10).pack(side=tk.LEFT,padx=30,pady=10)
        tk.Button(dlg,text="Register",command=do_reg,width=10).pack(side=tk.RIGHT,padx=30,pady=10)
    def _signout(self):
        if self.user:
            self.user=None; self.user_lbl.config(text="Not signed in")
            messagebox.showinfo("Signed out","You are now signed out.")

if __name__=="__main__":
    app=MIBro(); app.mainloop()
