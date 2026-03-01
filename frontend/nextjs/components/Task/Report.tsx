import React, { useEffect, useState } from 'react';
import { markdownToHtml } from '../../helpers/markdownHelper';
import '../../styles/markdown.css';
import { useTranslations } from "next-intl";

export default function Report({report}:any) {
    const t = useTranslations();
    const [htmlContent, setHtmlContent] = useState('');

    useEffect(() => {
        const convertMarkdownToHtml = async () => {
            try {
                const processedHtml = await markdownToHtml(report);
                setHtmlContent(processedHtml);
            } catch (error) {
                console.error('Error converting markdown to HTML:', error);
                setHtmlContent(`<p>${t("errors.somethingWentWrong")}</p>`);
            }
        };

        if (report) {
            convertMarkdownToHtml();
        }
    }, [report, t]);

    return (
        <div>
            <h2>{t("report.researchReportTitle")}</h2>
            <div id="reportContainer" className="markdown-content">
                <div dangerouslySetInnerHTML={{ __html: htmlContent }} />
            </div>
        </div>
    );
};
