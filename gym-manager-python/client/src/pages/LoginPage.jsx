import { useState } from "react";
import { Dumbbell } from "lucide-react";
import { useAuth } from "../app/AuthContext";
import { Button } from "../components/ui/Button";
import { Field, Input } from "../components/ui/Form";

export function LoginPage() {
  const { login, loginPending } = useAuth();
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    username: "admin",
    password: "PulseFit@2026",
  });
  const submit = async (event) => {
    event.preventDefault();
    setError("");
    try {
      await login(form);
    } catch (reason) {
      setError(reason.message);
    }
  };
  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="login-brand">
          <div className="brand-mark">
            <Dumbbell size={20} />
          </div>
          <div>
            <strong>PulseFit</strong>
            <span>Gym Management</span>
          </div>
        </div>
        <div className="login-copy">
          <p className="eyebrow">Vận hành phòng gym</p>
          <h1>Đăng nhập hệ thống</h1>
          <p>
            Quản lý hội viên, điểm danh DAH, công nợ và lịch PT trong một không gian
            làm việc thống nhất.
          </p>
        </div>
        <form onSubmit={submit} className="login-form">
          <Field label="Tên đăng nhập" required>
            <Input
              autoComplete="username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </Field>
          <Field label="Mật khẩu" required>
            <Input
              type="password"
              autoComplete="current-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          {error && (
            <div className="inline-error" role="alert">
              {error}
            </div>
          )}
          <Button
            type="submit"
            loading={loginPending}
            loadingText="Đang xác thực…"
          >
            Đăng nhập
          </Button>
        </form>
        <p className="login-help">
          Tài khoản mặc định có thể thay đổi qua biến môi trường máy chủ.
        </p>
      </section>
      <aside className="login-aside">
        <div>
          <span className="aside-rule" />
          <blockquote>
            “Phần mềm vận hành tốt phải giúp nhân viên nhìn thấy việc cần làm
            tiếp theo, không bắt họ đi tìm.”
          </blockquote>
          <p>Operational clarity, every day.</p>
        </div>
      </aside>
    </main>
  );
}
