pub fn print_title(value: &str) {
    println!("{value}");
}

pub fn print_status(label: &str, ok: bool) {
    let status = if ok { "ok" } else { "blocked" };
    println!("{label}={status}");
}

pub fn print_key_value(key: &str, value: &str) {
    println!("{key}={value}");
}
