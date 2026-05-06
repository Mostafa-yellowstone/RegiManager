import sys

file_path = r'c:\Users\mystr\RegiManager\templates\base.html'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_footer = """    {% block site_footer %}
    <footer class="site-footer" role="contentinfo" style="background: #0f172a; padding: 4rem 0 2rem; color: #94a3b8; font-family: 'Inter', sans-serif;">
        <div class="site-footer-inner" style="max-width: 1200px; margin: 0 auto; padding: 0 2rem;">
            <div class="site-footer-top" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 4rem; padding-bottom: 3rem; border-bottom: 1px solid rgba(255,255,255,0.1);">
                
                <!-- Column 1: Brand -->
                <div class="site-footer-brand">
                    <a href="{% url 'home' %}" style="display: inline-block; margin-bottom: 1.5rem;">
                        <img src="{% static 'core/img/regimanager-logo.svg' %}" alt="RegiManager" style="height: 40px; width: auto; filter: brightness(0) invert(1);">
                    </a>
                    <p style="color: #cbd5e1; font-size: 0.95rem; line-height: 1.6; max-width: 350px; margin-bottom: 2rem;">
                        {% trans "Operations software for Agencies records, receipts, dealers, and reporting in one unified workspace." %}
                    </p>
                    <div style="display: flex; gap: 1rem;">
                        <a href="#" style="color: #94a3b8; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">
                            <svg width="22" height="22" fill="currentColor" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
                        </a>
                        <a href="#" style="color: #94a3b8; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">
                            <svg width="22" height="22" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z"/></svg>
                        </a>
                    </div>
                </div>

                <!-- Column 2: Platform -->
                <div class="site-footer-col" style="display: flex; flex-direction: column; gap: 1rem;">
                    <h3 style="color: white; font-size: 1rem; font-weight: 600; margin-bottom: 0.5rem; letter-spacing: 0.5px; text-transform: uppercase;">{% trans "Platform" %}</h3>
                    <a href="{% url 'home' %}#home" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Overview" %}</a>
                    <a href="{% url 'home' %}#solutions" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Solutions" %}</a>
                    <a href="{% url 'home' %}#pricing" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Pricing" %}</a>
                    <a href="{% url 'contact' %}" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Contact Us" %}</a>
                    <a href="{% url 'privacy' %}" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Privacy Policy" %}</a>
                </div>

                <!-- Column 3: Access -->
                <div class="site-footer-col" style="display: flex; flex-direction: column; gap: 1rem;">
                    <h3 style="color: white; font-size: 1rem; font-weight: 600; margin-bottom: 0.5rem; letter-spacing: 0.5px; text-transform: uppercase;">{% trans "Access" %}</h3>
                    {% if user.is_authenticated %}
                    <a href="{% url 'dashboard' %}" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Dashboard" %}</a>
                    <a href="{% url 'logout' %}" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Sign out" %}</a>
                    {% else %}
                    <a href="{% url 'login' %}" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Sign in" %}</a>
                    <a href="{% url 'member-signup' %}" style="color: #94a3b8; text-decoration: none; font-size: 0.95rem; transition: color 0.2s;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#94a3b8'">{% trans "Create agent account" %}</a>
                    {% endif %}
                </div>
            </div>

            <div class="site-footer-bottom" style="display: flex; justify-content: space-between; align-items: center; padding-top: 2rem; font-size: 0.85rem; flex-wrap: wrap; gap: 1rem;">
                <p style="margin: 0; color: #64748b;">&copy; {% now "Y" %} Xpress Business Group. All rights reserved.</p>
                <p style="margin: 0; color: #475569; font-style: italic;">{% trans "This software solution is not affiliated with or endorsed by the DMV." %}</p>
            </div>
        </div>
    </footer>
    {% endblock site_footer %}
"""

out_lines = lines[:19] + [new_footer] + lines[80:]

with open(file_path, 'w', encoding='utf-8') as f:
    for line in out_lines:
        if not line.endswith('\n'):
            line += '\n'
        f.write(line)
