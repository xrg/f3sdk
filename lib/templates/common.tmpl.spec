{% block prologue %}
{% if autonomous %}
%define git_repo {{ git_repo or name }}
%define git_head {{ git_head or 'HEAD' }}
{% if git_source_subpath %}
%define git_source_subpath {{ git_source_subpath }}
{% endif %}
{% endif %}
{% endblock %}

%{!?pyver: %global pyver %(python -c 'import sys;print(sys.version[0:3])')}
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

%define release_class {{ release_class }}
%define debug_package %{nil}

{% for module in modules %}
{{ module.rpm.globals }}
{% endfor %}

{% block definitions %}
Name:           {{name}}
License:        {{ license or 'AGPLv3' }}
Group:          Databases
Summary:        Addons for OpenERP/F3
{% if autonomous %}
Version:        %git_get_ver
Release:        %mkrel %git_get_rel2
Source0:        %git_bs_source %{name}-%{version}.tar.gz
Source1:        %{name}-gitrpm.version
Source2:        %{name}-changelog.gitrpm.txt
{% else %}
Version:        {{rel.mainver+rel.subver }}
Release:        %mkrel {{ rel.extrarel }}
#Source0:       %{name}-%{version}.tar.gz
{% endif %}
URL:            {{ project_url or 'http://openerp.hellug.gr' }}
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}
BuildArch:      noarch
{% endblock %}
{% for module in modules %}
{{ module.rpm.main }}
{% endfor %}


{% block main_description %}
{# This description won't be used anyway #}
%description
Addon modules for OpenERP
{% endblock %}

{% block extra_modules %}
{% endblock %}

%prep
{% block prep %}
{% if autonomous %}
%git_get_source
%setup -q
{% else %}
%setup -T -D -n %{name}-%{version}
{% endif %}
{% endblock %}
{% for module in modules %}
{{ module.rpm.prep }}
{% endfor %}

%build
{% block build %}
{% endblock %}
{% for module in modules %}
{{ module.rpm.build }}
{% endfor %}


%install
[ -n "%{buildroot}" ] && rm -rf %{buildroot}

{% block install %}
install -d %{buildroot}/%{python_sitelib}/openerp-server/addons
cp -ar {{ git_source_subpath or addons_subpath or '.' }}/* %{buildroot}/%{python_sitelib}/openerp-server/addons/

{% if modules.no_dirs %}
pushd %{buildroot}/%{python_sitelib}/openerp-server/addons/
{% for tdir in modules.no_dirs %}
    {% if tdir %}
        rm -rf {{ tdir }}
    {% endif %}
{% endfor %}
popd
{% endif %}
{% endblock %}
{% for module in modules %}
{{ module.rpm.install }}
{% endfor %}
{% block extra_install %}
{% endblock %}

{% for module in modules %}
{% if not module.installable %}
    {%- continue %}
{% endif %}
%package {{ module.name }}
{% if module.info.version %}
Version: {{ module.info.version }}
{% endif %}
Group: Databases
Summary: {{ module.info.name }}
AutoReqProv:       no
Requires: python(abi) = %pyver
Requires: openerp-server {% if rel.mainver %}>= {{ rel.mainver }}{% endif %}

{% if name != 'openerp-addons' %}
Provides: openerp-addons-{{ module.name }}
{% endif %}

{% if module.info.depends %}
{{ module.get_depends() }}
{% endif -%}
{%- if module.ext_deps %}
{{ module.ext_deps }}
{% endif -%}
{% if module.info.author %}
Vendor: {{module.info.author }}
{% endif %}
{% if module.info.website %}
URL: {{ module.get_website() }}
{% endif %}
{{ module.rpm.package }}


%description {{ module.name }}
{{ module.info.description or module.info.name }}
{{ module.rpm.description }}

{% if module.rpm.pre %}
%pre {{ module.name }}
{{ module.rpm.pre }}
{% endif %}

{% if module.rpm.preun %}
%preun {{ module.name }}
{{ module.rpm.preun }}
{% endif %}

{% if module.rpm.post %}
%post {{ module.name }}
{{ module.rpm.post }}
{% endif %}

{% if module.rpm.postun %}
%postun {{ module.name }}
{{ module.rpm.postun }}
{% endif %}

%files {{ module.name }}
%defattr(-,root,root)
%{python_sitelib}/openerp-server/addons/{{ module.name }}
{{ module.rpm.files }}

{% endfor %}

{% block extra_files %}
{% endblock %}

{% for module in modules %}
{# new iteration, may include uninstallable modules #}
{{ module.rpm.extrapkgs }}
{% endfor %}

{% if autonomous %}
%changelog -f %{_sourcedir}/%{name}-changelog.gitrpm.txt
{% endif %}

#eof
