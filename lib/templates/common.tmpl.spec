{% block prologue %}
{% if autonomous %}
%define git_repo {{ git_repo or name }}
%define git_head {{ git_head or 'HEAD' }}
{% if git_source_subpath %}
%define git_source_subpath {{ git_source_subpath }}
{% endif %}
%define cd_if_modular :
{% else %}
%define cd_if_modular cd %{name}-%{version}
{% endif %}
{% endblock %}

%{!?pyver: %global pyver %(python -c 'import sys;print(sys.version[0:3])')}
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

%define release_class {{ release_class }}

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
cd %{name}-%{version}
{% endif %}
{% endblock %}

%build
%{cd_if_modular}
{% block build %}
{% endblock %}

%install
%{cd_if_modular}
rm -rf $RPM_BUILD_ROOT

{% block install %}
install -d $RPM_BUILD_ROOT/%{python_sitelib}/openerp-server/addons
cp -ar {{ git_source_subpath or addons_subpath or '.' }}/* $RPM_BUILD_ROOT/%{python_sitelib}/openerp-server/addons/

{% if modules.no_dirs %}
pushd $RPM_BUILD_ROOT/%{python_sitelib}/openerp-server/addons/
{% for tdir in modules.no_dirs %}
    {% if tdir %}
        rm -rf {{ tdir }}
    {% endif %}
{% endfor %}
popd
{% endif %}
{% endblock %}
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

%description {{ module.name }}
{{ module.info.description or module.info.name }}


%files {{ module.name }}
%defattr(-,root,root)
%{python_sitelib}/openerp-server/addons/{{ module.name }}

{% endfor %}

{% block extra_files %}
{% endblock %}

{% if autonomous %}
%changelog -f %{_sourcedir}/%{name}-changelog.gitrpm.txt
{% endif %}

#eof
