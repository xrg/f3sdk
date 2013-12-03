%define git_repo f3sdk

%define f3sdkdir %{_prefix}/lib/f3sdk

Name:       f3sdk
Summary:    Software Development Kit for F3-ERP
Version:    %git_get_ver
Release:    %mkrel %git_get_rel
URL:        https://github.com/xrg/f3sdk
Source0:    %git_bs_source %{name}-%{version}.tar.gz
License:    LGPLv3
BuildArch:  noarch
Group:      Libraries
BuildRequires:  python
Requires:   python-jinja2 >= 2.4

%description
A collection of scripts, utilities for F3-ERP (and OpenERP) developers
or packagers.

These scripts are NOT needed for a production server, but rather for the
developer's workstation.


%prep
%git_get_source
%setup -q

%build

cat > ./bin/f3-modulize << EOF
#!/bin/bash

exec %{f3sdkdir}/modulize.py "$$@"
EOF


%install
install -d %{buildroot}%{_bindir}/
install bin/* %{buildroot}%{_bindir}/
install -d %{buildroot}%{f3sdkdir}
cp -ar lib/* %{buildroot}%{f3sdkdir}/



%files
%attr(0755,root,root) %{_bindir}/f3*
%defattr(-,root,root)
%doc README.md
%dir %{f3sdkdir}
%{f3sdkdir}/*

%changelog -f %{_sourcedir}/%{name}-changelog.gitrpm.txt

